"""Bind the automatic proposal/check policy independently from historical certificates."""
import hashlib
from pathlib import Path

from davcore.ast import digest
from davcore.versioning import backend_binding


def policy_binding() -> str:
    root = Path(__file__).parent
    return digest({'DAV_backend': backend_binding(), 'coordinator': {
        name: hashlib.sha256((root/name).read_bytes()).hexdigest()
        for name in ['contract.py', 'journal.py', 'planner.py', 'checker.py', 'controller.py', 'intake.py', 'versioning.py',
            'artifact.py','artifact_contract.py','semantic011.py','semantic014.py']},'artifact_profiles':{
                name:hashlib.sha256((root.parent/'semantic_repair'/name).read_bytes()).hexdigest()
                for name in ['compiler.py','contract.py','realization.py','observe009.py','observe008.py','observe005.py','alignment.py',
                    'context009.py','runtime009.py','check009.py','trace008.py','worker.py',
                    'relations011.py','prompts011.py','inference011.py','observe011.py','realization011.py','check011.py',
                    'relations012.py','prompts012.py','observe012.py','realization012.py','check012.py',
                    'observer013_contract.py','relations013.py','prompts013.py','observe013.py','inference013.py','reference013.py','report013.py',
                    'meaning014_contract.py','meaning014.py','prompts014.py','meaning014_reference.py']}})
