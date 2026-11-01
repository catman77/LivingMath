"""Append-only local experiment log; IDs are explicitly local, not fake MCP IDs."""
import json
from pathlib import Path
from typing import Any
from davcore.ast import digest


class Journal:
    def __init__(self,path: Path):
        self.path=path
        if path.exists():raise FileExistsError('EXPERIMENT_COHORT_ALREADY_EXISTS')
        self.previous='0'*64;self.sequence=0

    def append(self,kind: str,payload: dict) -> dict:
        row: dict[str,Any]={'local_sequence':self.sequence,'kind':kind,'payload':payload,'previous_hash':self.previous}
        row['entry_hash']=digest(row)
        with self.path.open('a') as stream:stream.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+'\n')
        self.previous=row['entry_hash'];self.sequence+=1;return row

    @staticmethod
    def verify(path: Path) -> dict:
        previous='0'*64;count=0
        for line in path.read_text().splitlines():
            row=json.loads(line);actual=row.pop('entry_hash')
            if row['previous_hash']!=previous or digest(row)!=actual or row['local_sequence']!=count:
                raise ValueError('LOCAL_APPEND_ONLY_CHAIN_BROKEN')
            previous=actual;count+=1
        return {'ok':True,'entries':count,'head_hash':previous,'identity_scope':'LOCAL_EXPERIMENT_NOT_MCP_ID'}
