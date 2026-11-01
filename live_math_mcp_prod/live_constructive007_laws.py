"""Source-specific proof-schema validation. No target pair, suffix search or oracle."""
from dataclasses import dataclass
from math import gcd

from normalizer import digest
from live_constructive007_native import native_fingerprint,AUDITED_IMPLEMENTATION
from live_constructive007_source import payload,ref_id

FIELDS={'schema','source_ref','source_hash','project','scope','version','observer_hash','native_hash','kind','coverage','guard'}


@dataclass
class LawView:
    width: int
    coordinate_actions: dict
    proof: str
    receipt: dict

    def features(self,state,ledger):
        ledger.charge('feature_reads',self.width)
        if len(state.value)>self.width:raise ValueError('FEATURE_GUARD')
        return list(state.value)+['EMPTY']*(self.width-len(state.value))


def verify(frame,certificate_ref,ledger):
    ledger.stage='law_validation'
    if certificate_ref is None:return None,{'status':'REJECTED','reason':'MISSING_LAW'}
    try:
        event=frame.events[ref_id(certificate_ref)];cert=payload(event)['source_certificate'];ledger.charge('certificate_fields',len(cert))
        if set(cert)!=FIELDS or cert['schema']!='separating-coordinate/v1':raise ValueError('LAW_SCHEMA')
        root=frame.events[ref_id(frame.query['root_ref'])]
        expected=(frame.query['root_ref'],digest(root),frame.query['project'],frame.query['scope'],frame.query['version'],digest(frame.spec['observer']))
        actual=tuple(cert[k] for k in ('source_ref','source_hash','project','scope','version','observer_hash'))
        if actual!=expected:raise ValueError('LAW_SOURCE_SCOPE_VERSION_OBSERVER')
        actual_native=native_fingerprint();ledger.charge('native_definition_hashes',3)
        if actual_native!=AUDITED_IMPLEMENTATION or cert['native_hash']!=actual_native or frame.spec['primitive_sha256']!=actual_native:raise ValueError('UNAUDITED_NATIVE_DEFINITION')
        if frame.spec['observer']!={'projection':'primary','mod':None}:raise ValueError('LAW_OBSERVER_GUARD')
        p=frame.spec['parameters'];mapping={};ledger.charge('parameter_bytes',len(str(p).encode()))
        if cert['kind']=='affine-injective' and p['family']=='affine':
            m=p['modulus'];width=2
            if type(m) is not int or m<2 or len(p['initial'])!=2 or any(type(x) is not int or not 0<=x<m for x in p['initial']) or cert['guard']!={'total_admissibility':True,'width':2}:raise ValueError('AFFINE_GUARD')
            for i,k in enumerate(p['coefficients']):
                ledger.charge('gcd_checks')
                if type(k) is not int:raise ValueError('AFFINE_COEFFICIENT')
                if gcd(k,m)==1:mapping.setdefault(1,i)
            proof='For equal x, delta O after k equals k*delta y modulo m; gcd(k,m)=1 makes multiplication injective. Native y update is irrelevant to this one-step statement.'
        elif cert['kind']=='right-projection' and p['family']=='permutation':
            width=len(p['initial'])
            if cert['guard']!={'total_admissibility':True,'width':width}:raise ValueError('PERM_GUARD')
            for i,g in enumerate(p['permutations']):
                ledger.charge('permutation_entries',len(g))
                if sorted(g)!=list(range(width)):raise ValueError('NOT_A_PERMUTATION')
                mapping.setdefault(g[0],i)
            proof='Native right composition gives (v composed with g)[0]=v[g[0]]. No commuting or reordering of generators is used.'
        elif cert['kind']=='prefix-projection' and p['family']=='erasure':
            width=len(p['initial'])
            if cert['guard']!={'total_admissibility':True,'width':width} or 'EMPTY' in p['initial']:raise ValueError('ERASURE_GUARD')
            for i,j in enumerate(p['cuts']):
                ledger.charge('cut_checks')
                if type(j) is not int or not 0<=j<=width:raise ValueError('CUT_GUARD')
                if j<width:mapping.setdefault(j,i)
            proof='For total prefix deletion, head(drop_j(word)) is padded_word[j]; later words never exceed the declared initial width. Absorption is not invertible.'
        else:raise ValueError('NO_SUPPORTED_PROOF_SCHEMA')
        coverage=cert['coverage']
        if not isinstance(coverage,list) or len(set(coverage))!=len(coverage) or any(type(i) is not int or not 0<=i<width for i in coverage):raise ValueError('LAW_COVERAGE')
        mapping={i:a for i,a in mapping.items() if i in coverage}
        receipt={'status':'SOURCE_SCHEMA_CERTIFIED','source_ref':certificate_ref,'source_hash':digest(event),
            'proof_scope':'Reviewed implementation schema and declared parameter guard, not a universal proof checker or server verification.',
            'kind':cert['kind'],'coverage':coverage,'realized_coordinates':sorted(mapping),'native_validation_calls':0,'proof':proof}
        return LawView(width,mapping,proof,receipt),receipt
    except (KeyError,ValueError,TypeError) as error:
        return None,{'status':'REJECTED','reason':str(error)}
