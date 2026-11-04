"""Use the original immutable001 contracts; no copied verifier edits."""
from pathlib import Path
import sys
CHECKER_DIR=Path(__file__).resolve().parent/'checker001'
if str(CHECKER_DIR) not in sys.path:sys.path.insert(0,str(CHECKER_DIR))
from contracts import canonical,digest,byte_digest,strict_json,load,save,source_ref,verifier_digest
EXPECTED_VERIFIER='a035303149c1307126ff26e4bf60725daf3b104598be8a04a958e14388a61f08'


def binder_digest() -> str:
    root=Path(__file__).parent
    return digest({name:byte_digest((root/name).read_bytes()) for name in ['common002.py','proposal_schema.py','proposal_binder.py','PROPOSAL_DELTA_V1.schema.json']})
