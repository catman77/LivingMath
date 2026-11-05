"""Finite JSON-field distinguishability, never an oracle for literary meaning."""
from ..core import canonical,digest
from ..errors import AssuranceError
from .records import seal

BOUNDARY='Only declared annotations, the explicit finite record domain and fully enumerated Q; no world/author-meaning equivalence.'


def field(record,path):
    if not isinstance(path,str) or not path.startswith('/'):
        raise AssuranceError('QUERY_FIELD_NOT_CHECKED')
    value=record['declared_observables']
    try:
        for token in path.split('/')[1:]:
            token=token.replace('~1','/').replace('~0','~')
            value=value[int(token)] if isinstance(value,list) else value[token]
        # This one field is explicitly a set, other lists keep their exact order.
        return sorted(value) if path=='/image_set' else value
    except (KeyError,IndexError,ValueError,TypeError):
        raise AssuranceError('QUERY_FIELD_NOT_CHECKED') from None


def evaluate(contract,left,right,projection_ref):
    records=[left,right];queries=contract['declared_Q'];domain=contract['domain_refs']
    status='UNDETERMINED';reason='Q_NOT_SPECIFIED';projected=[];lost=[];different=[];preserved=[];pairs=checked=0
    if any(q['kind']=='SEMANTIC_QUESTION' for q in queries):
        status='HYPOTHESIZED_SEMANTIC_LOSS';reason='SEMANTIC_QUERY_NOT_VERIFIABLE'
    elif queries and not contract['Q_complete']:
        status='NOT_CHECKED';reason='DECLARED_Q_NOT_EXHAUSTIVE'
    elif queries:
        try:
            projected=[{p:field(r,p) for p in contract['projection_fields']} for r in records]
            for q in queries:
                values=[field(r,q['field']) for r in records];checked+=1
                if canonical(values[0])!=canonical(values[1]):different.append(q['field'])
                else:preserved.append(q['field'])
                if canonical(projected[0])==canonical(projected[1]) and canonical(values[0])!=canonical(values[1]):
                    lost.append({'q':q,'u':domain[0],'v':domain[-1],'P_u':projected[0],'P_v':projected[1],
                                 'q_u':values[0],'q_v':values[1]})
            # Explicit exhaustive evaluation of all ordered pairs in this finite domain.
            pairs=len(domain)**2
            status='LOSS_DETECTED' if lost else 'PRESERVED_FOR_DECLARED_Q'
            reason='EQUAL_PROJECTION_DIFFERENT_DECLARED_QUERY' if lost else 'EXHAUSTIVE_DECLARED_TWO_RECORD_DOMAIN'
        except AssuranceError:
            status='NOT_CHECKED';reason='QUERY_OR_PROJECTION_FIELD_NOT_CHECKED';lost=[];pairs=0
    if contract['expectation']=='PRESERVED_FOR_DECLARED_Q' and status=='LOSS_DETECTED':
        status='REJECTED';reason='FALSE_STRUCTURAL_PRESERVATION'
    elif contract['expectation']=='LOSS_DETECTED' and status=='PRESERVED_FOR_DECLARED_Q':
        status='REJECTED';reason='FALSE_STRUCTURAL_LOSS'
    return seal('loss-witness',contract['project_id'],contract['source_snapshot_digest'],{
        'projection_ref':projection_ref,'status':status,'reason_code':reason,'projected_values':projected,
        'different_fields':sorted(set(different)),'preserved_fields':sorted(set(preserved)),
        'lost_queries':lost,'checked_query_count':checked,'checked_pair_count':pairs,'domain_refs':domain,
        'source_anchor_refs':sorted({a for f in records for c in f['claim_atoms'] for a in c['source_anchor_refs']}),
        'uncertainty':['Annotations are proposed readings, not certified author intention or physical identity.'],
        'assurance_boundary':BOUNDARY},producer=projection_ref,parents=[projection_ref,*domain])
