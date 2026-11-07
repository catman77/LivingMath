"""Data-only frozen replay; no provider, code evaluation or network access."""
import argparse
import json
from pathlib import Path
from lm_suti_assurance.core import digest
from lm_suti_assurance.nl_proposal.causal import redecode
from lm_suti_assurance.nl_proposal.causal_service import deterministic


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('bundle',type=Path)
    p.add_argument('--expected-bundle-sha256',required=True,help='Trusted manifest SHA; self-reported receipts are not signatures')
    a=p.parse_args()
    raw=a.bundle.read_bytes()
    import hashlib
    if len(raw)>32*1024*1024 or hashlib.sha256(raw).hexdigest()!=a.expected_bundle_sha256:
        raise SystemExit('REJECTED_PROVENANCE: bundle bytes differ from trusted manifest')
    b=json.loads(raw)
    if b.get('schema')!='nl-causal-bundle/1':raise SystemExit('INVALID_BUNDLE')
    value=redecode(b['source_bundle'],b['source_item_indices'],b['structural'],b['arms'],b['policy'])
    actual=digest(deterministic(value))
    result={'status':'REPLAY_MATCH' if actual==b['expected_sha256'] else 'REPLAY_BOUND_DIVERGENCE',
            'actual_sha256':actual,'expected_sha256':b['expected_sha256'],'LLM_calls':0,'network_calls':0,'execution_permission':False}
    print(json.dumps(result,sort_keys=True))
    if result['status']!='REPLAY_MATCH':raise SystemExit(1)

if __name__=='__main__':main()
