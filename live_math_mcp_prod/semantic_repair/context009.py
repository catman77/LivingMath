"""Server-minted project/source context; never accepted as a public MCP argument."""
from dataclasses import dataclass
import hashlib
import json

from artifact_genesis.contract import RawPacket
from davcore.ast import digest
from davcore.service import Service

_MINT=object()


@dataclass(frozen=True)
class VerifiedSource:
    project: str
    record: dict
    _authority: object
    _references: frozenset[str] | None = None

    def require(self, project: str, premises: list[dict] | None = None) -> None:
        if self._authority is not _MINT or project!=self.project:
            raise ValueError('AUTHENTICATED_SOURCE_CONTEXT_REQUIRED')
        if premises is not None:
            allowed=self._references if self._references is not None else {s['id'] for packet in packets(self)[0] for s in packet['spans']}
            if any(p['source_hash']!=self.record['payload']['sha256'] or not set(p['source_refs'])<=allowed for p in premises):
                raise ValueError('FOREIGN_OR_UNADDRESSED_SOURCE_PREMISE')

    def public(self) -> dict:
        p=self.record['payload']
        return {'project':self.project,'snapshot_id':self.record['id'],'snapshot_entry_hash':self.record['entry_hash'],
            'namespace':p['namespace'],'version':p['version'],'sha256':p['sha256'],'edition':p['edition']}

    def transport(self, premises: list[dict]) -> dict:
        self.require(self.project,premises)
        return {'schema':'server-context009/1','source':self.public(),
            'admitted_refs':sorted({r for p in premises for r in p['source_refs']})}


def from_server_record(project: str, row: dict) -> VerifiedSource:
    """Called only after Store.get(project,id), or on the private worker channel.

    The worker channel is not a tool: the authenticated server resolves the row;
    clients cannot submit this envelope through ArtifactInput/CompilerRequest.
    """
    Service.project(project)
    body={k:v for k,v in row.items() if k not in {'entry_hash','payload'}}
    if row.get('project')!=project or row.get('kind')!='artifact_source' or digest(body)!=row.get('entry_hash'):
        raise ValueError('SOURCE_RECORD_OWNERSHIP_OR_HASH_MISMATCH')
    p=json.loads(row['payload_json'])
    if p!=row['payload'] or hashlib.sha256(p['raw_text'].encode()).hexdigest()!=p['sha256']:
        raise ValueError('SOURCE_RAW_BYTES_HASH_MISMATCH')
    return VerifiedSource(project,row,_MINT)


def resolve(store, project: str, ident: int) -> VerifiedSource:
    return from_server_record(project,store.get(project,ident))


def from_private_channel(value: dict) -> VerifiedSource:
    """Consume the trusted subprocess pipe, after the parent Store resolution.

    No public request schema accepts this object. Full raw bytes stay in Store;
    transmitting them twice would waste the inherited 64 KB worker cap.
    """
    if set(value)!={'schema','source','admitted_refs'} or value['schema']!='server-context009/1':
        raise ValueError('PRIVATE_SERVER_SOURCE_CONTEXT_REQUIRED')
    p=value['source'];Service.project(p['project'])
    row={'id':p['snapshot_id'],'entry_hash':p['snapshot_entry_hash'],'payload':p}
    return VerifiedSource(p['project'],row,_MINT,frozenset(value['admitted_refs']))


def packets(context: VerifiedSource) -> tuple[list[dict],list[dict]]:
    """Exact UTF-8 addresses, including CRLF widths; no synthetic fixture factory."""
    context.require(context.project)
    p=context.record['payload'];raw=p['raw_text'];unsupported=[];offset=0
    name='artifact_'+p['namespace'][:24];groups=[];group=[]
    for i,line in enumerate(raw.splitlines(keepends=True)):
        text=line.rstrip('\r\n');width=len(line.encode());end=offset+len(text.encode())
        if text and len(text)>4096:
            unsupported.append({'start':offset,'end':end,'reason':'SOURCE_LINE_EXCEEDS_4096_CHARACTERS'})
        elif text.strip():
            group.append({'id':name+':line'+str(i+1),'document_id':name,'document_sha256':p['sha256'],
                'edition':p['edition'],'start':offset,'end':end,'text':text,
                'source_address':{'line':i+1,'section':p['namespace'],'snapshot_version':p['version']}})
        else:
            if group:groups.append(group);group=[]
        offset+=width
    if group:groups.append(group)
    windows=[group[i:i+8] for group in groups for i in range(0,len(group),8)]
    out=[]
    for i,window in enumerate(windows):
        packet=RawPacket.model_validate({'id':name+':window'+str(i),'document_id':name,
            'document_sha256':p['sha256'],'edition':p['edition'],'language':p['language'],'spans':window})
        out.append(packet.model_dump())
    return out,unsupported
