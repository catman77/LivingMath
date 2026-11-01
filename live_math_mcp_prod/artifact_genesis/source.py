"""Owner-frozen raw bytes and enforced precommit/reveal boundary."""
import hashlib
import json
from pathlib import Path
from typing import Any
from davcore.ast import digest
from .contract import RawPacket


def save(path: Path,value) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def packet_from_text(name: str,text: str,language: str='en') -> RawPacket:
    sha=hashlib.sha256(text.encode()).hexdigest();rows=[];offset=0
    for i,line in enumerate(text.splitlines()):
        if line:rows.append({'id':name+':line'+str(i),'document_id':name,'document_sha256':sha,'edition':'ORIGINAL_SYNTHETIC_FIXTURE',
            'start':offset,'end':offset+len(line.encode()),'text':line,'source_address':{'line':i+1}})
        offset+=len(line.encode())+1
    return RawPacket.model_validate({'id':name,'document_id':name,'document_sha256':sha,'edition':'ORIGINAL_SYNTHETIC_FIXTURE',
                                    'language':language,'spans':rows,'context':[]})


class SourceVault:
    def __init__(self,root: Path):
        self.root=Path(root).resolve();self.catalog=json.loads((self.root/'frozen/catalog.json').read_text())
        self.freeze=json.loads((self.root/'source-freeze.json').read_text())
        for name,sha in self.freeze['frozen_files'].items():
            p=(self.root/name).resolve(strict=True)
            if not p.is_relative_to(self.root) or hashlib.sha256(p.read_bytes()).hexdigest()!=sha:
                raise ValueError('SOURCE_FREEZE_DRIFT:'+name)
        self._seal: dict[str,Any]|None=None;self.access: list[dict[str,Any]]=[]

    def packet(self,ident: str,*,seal: dict|None=None) -> RawPacket:
        if ident not in self.catalog:raise ValueError('UNKNOWN_SOURCE_PACKET')
        meta=self.catalog[ident]
        if meta['partition']=='holdout':
            if seal is None:raise PermissionError('HOLDOUT_BEFORE_PREDICTION_SEAL')
            if self._seal is None or seal!=self._seal:raise ValueError('INVALID_HOLDOUT_SEAL')
        raw=json.loads((self.root/meta['path']).read_text())
        data=(self.root/meta['document_path']).read_bytes()
        if hashlib.sha256(data).hexdigest()!=meta['document_sha256']:raise ValueError('DOCUMENT_HASH_DRIFT')
        if raw['document_sha256']!=meta['document_sha256'] or raw['edition']!=meta['edition']:raise ValueError('SOURCE_EDITION_DRIFT')
        for span in raw['spans']+raw.get('context',[]):
            if data[span['start']:span['end']]!=span['text'].encode():raise ValueError('SOURCE_SLICE_DRIFT')
        grammar=self.root/'frozen/grammar-cues.json'
        if grammar.exists():raw['grammar']=json.loads(grammar.read_text())[raw['language']]
        self.access.append({'packet_id':ident,'partition':meta['partition'],'after_seal':self._seal is not None,
                            'packet_sha256':digest(raw)})
        return RawPacket.model_validate(raw)

    def seal(self,predictions: list[dict]) -> dict:
        if self._seal is not None:raise ValueError('SEAL_ALREADY_COMMITTED')
        if not predictions or any(not p.get('target_free') for p in predictions):raise ValueError('SOURCE_PREDICTIONS_REQUIRED')
        body={'prediction_sha256':digest(predictions),'source_freeze_sha256':hashlib.sha256((self.root/'source-freeze.json').read_bytes()).hexdigest(),
              'prediction_count':len(predictions),'kind':'SOURCE_PREDICTION_SEAL'}
        self._seal={**body,'seal_sha256':digest(body)}
        return dict(self._seal)


def build_fixture_vault(root: Path) -> Path:
    root=Path(root);(root/'frozen').mkdir()
    catalog={}
    for name,part in [('train','train'),('hidden','holdout')]:
        text='If the signal appears, the latch opens.\n';p=packet_from_text(name,text)
        save(root/'frozen'/(name+'.json'),p.model_dump());(root/'frozen'/(name+'.txt')).write_text(text)
        catalog[name]={'partition':part,'path':'frozen/'+name+'.json','document_path':'frozen/'+name+'.txt',
                       'document_sha256':p.document_sha256,'edition':p.edition}
    save(root/'frozen/catalog.json',catalog)
    save(root/'source-freeze.json',{'frozen_files':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (root/'frozen').iterdir() if p.is_file()}})
    return root
