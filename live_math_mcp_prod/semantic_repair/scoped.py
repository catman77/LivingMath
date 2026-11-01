"""Claim identity and source comparison, alongside (not replacing) DAV's AST.

These records describe the human claim a model is intended to represent. They
are not an interpreter, truth oracle, or a second mathematical expression DSL.
"""
from typing import Literal

from davcore.ast import digest
from davcore.models import StrictModel


class Claim(StrictModel):
    predicate: str
    subject: str
    object: str
    domain: str
    quantifier: Literal['ALL', 'SOME', 'NAMED_CASE', 'UNKNOWN']
    polarity: Literal['POSITIVE', 'NEGATIVE', 'UNKNOWN']
    modality: str
    time: str
    stage: str
    scope: str
    source_hash: str
    edition: str
    assumptions: tuple[str, ...] = ()
    display: str = ''
    participant: str | None = None
    stimulus_participant: str | None = None
    recipient: str | None = None
    direction: str | None = None
    witness_id: str | None = None
    domain_members: tuple[str, ...] | None = None
    antecedent_nonempty: bool | None = None
    input_polarity: str | None = None
    discourse: str | None = None

    def identity(self) -> str:
        payload = self.model_dump(exclude={'display'})
        # Legacy roleless records retain their historical digest. New addressed
        # claims bind roles explicitly; missing roles are not inferred here.
        for key in ('participant', 'stimulus_participant', 'recipient', 'direction',
                    'witness_id', 'domain_members', 'antecedent_nonempty', 'input_polarity', 'discourse'):
            if payload[key] is None:
                payload.pop(key)
        return digest(payload)


def compare(claim: Claim, evidence_claim: Claim | None, refs: list[str]) -> dict:
    base = {'claim_id': claim.identity(), 'source_refs': refs, 'proof_status': 'unverified',
            'execution_permission': {'allowed': False}}
    if evidence_claim is None:
        return {**base, 'status': 'UNRESOLVED', 'reason': 'No source-addressed claim with a complete matching signature.'}
    a = claim.model_dump(exclude={'display'}); b = evidence_claim.model_dump(exclude={'display'})
    differences = [k for k in a if a[k] != b[k]]
    unknown = any(a[k] == 'UNKNOWN' or b[k] == 'UNKNOWN' for k in ['quantifier', 'polarity', 'modality', 'time', 'domain'])
    relation='UNDETERMINED'; qualification=None
    guards=('predicate','subject','object','domain','modality','time','stage','scope','source_hash','edition',
            'participant','stimulus_participant','recipient','direction','input_polarity','discourse','assumptions')
    same=all(a[k]==b[k] for k in guards)
    same_witness=bool(claim.witness_id and claim.witness_id==evidence_claim.witness_id)
    member=bool(evidence_claim.witness_id and evidence_claim.witness_id in (claim.domain_members or ()))
    if same and not unknown and claim.polarity!=evidence_claim.polarity:
        if claim.quantifier==evidence_claim.quantifier=='SOME' and not same_witness:
            status='COMPATIBLE_ONLY';relation='COMPATIBLE_DISTINCT_EXISTENTIAL_WITNESSES'
        elif claim.quantifier==evidence_claim.quantifier=='NAMED_CASE':
            status='REFUTES_EXACT_CLAIM' if same_witness else 'UNRESOLVED'
            relation='CONTRADICTION_SAME_ADDRESSED_WITNESS' if same_witness else 'WITNESS_IDENTITY_REQUIRED'
        elif claim.quantifier=='ALL' and evidence_claim.quantifier in {'NAMED_CASE','SOME'}:
            status='REFUTES_EXACT_CLAIM' if member else 'UNRESOLVED';relation='MEMBER_COUNTEREXAMPLE' if member else 'DOMAIN_MEMBERSHIP_REQUIRED'
        elif claim.quantifier=='SOME' and evidence_claim.quantifier=='ALL':
            status='REFUTES_EXACT_CLAIM';relation='EXISTENTIAL_VS_UNIVERSAL_NEGATION'
        elif claim.quantifier==evidence_claim.quantifier=='ALL':
            nonempty=claim.antecedent_nonempty is True or evidence_claim.antecedent_nonempty is True
            status='REFUTES_EXACT_CLAIM' if nonempty else 'UNRESOLVED'
            relation='OPPOSITE_RULES_NONEMPTY_DOMAIN' if nonempty else 'ANTECEDENT_NONEMPTY_REQUIRED'
            qualification='Opposite conditional rules can coexist on an empty antecedent domain.'
        else:
            status='REFUTES_EXACT_CLAIM' if same_witness else 'UNRESOLVED';relation='SAME_WITNESS_REQUIRED'
    elif same and not unknown and claim.polarity==evidence_claim.polarity:
        if claim.quantifier==evidence_claim.quantifier:
            status='SUPPORTS_EXACT_CLAIM' if claim.quantifier!='NAMED_CASE' or same_witness else 'UNRESOLVED'
            relation='SAME_SCOPED_ASSERTION' if status=='SUPPORTS_EXACT_CLAIM' else 'WITNESS_IDENTITY_REQUIRED'
        elif claim.quantifier=='SOME' and ((evidence_claim.quantifier=='ALL' and evidence_claim.antecedent_nonempty is True) or
                                        (evidence_claim.quantifier=='NAMED_CASE' and member)):
            status='SUPPORTS_EXACT_CLAIM';relation='EXISTENTIAL_WITNESS_OR_NONEMPTY_UNIVERSAL'
        else:
            status='COMPATIBLE_ONLY';relation='QUANTIFIER_STRENGTH_NOT_ESTABLISHED'
    elif not differences and not unknown:
        status = 'SUPPORTS_EXACT_CLAIM'
    elif a['predicate'] == b['predicate'] and a['subject'] == b['subject'] and a['object'] == b['object']:
        status = 'COMPATIBLE_ONLY'
    else:
        status = 'DIFFERENT_CLAIM'
    return {**base, 'status': status, 'evidence_claim_id': evidence_claim.identity(), 'differences': differences,
            'quantifier_relation':relation,'qualification':qualification,
            'reason': 'Exact scoped comparison; missing or different evidence is not refutation.'}


def composable(path: list[dict]) -> bool:
    """Only explicitly declared compositional readings; sequence is not cause."""
    if not any(p.get('semantics') for p in path):
        return True  # legacy contract remains reproducible, not retroactively stronger
    kinds = {p.get('semantics') for p in path}
    if kinds == {'NORMATIVE_CONNECTIVITY'}:
        return True
    if not kinds <= {'CONDITIONAL', 'CLASS_INSTANTIATION'}:
        return False
    # Distinct antecedent guards must not disappear when arrows are joined.
    if len({tuple(p.get('assumptions') or []) for p in path}) > 1:
        return False
    for p in path:
        for r in (p['src'], p['dst']):
            if any(r.get(k) in {None, 'UNKNOWN'} for k in ['domain', 'quantifier', 'polarity', 'participant', 'time']):
                return False
    return True


def from_query(query: dict, premises: list[dict], edition: str, *, operational: bool = False, role_bound: bool = False) -> Claim:
    by = {p['id']: p for p in premises}; path = [by[k] for k in query['premise_ids']]
    first, last = path[0]['src'], path[-1]['dst']
    roles={'participant':last.get('participant'),'stimulus_participant':first.get('participant'),
           'recipient':'scoped_predicate_target','direction':'FORWARD'} if role_bound else {}
    return Claim(predicate='OPERATIONAL_POSTCONDITION' if operational else
                 ('NORMATIVE_CONNECTIVITY' if all(p.get('semantics') == 'NORMATIVE_CONNECTIVITY' for p in path) else 'CONDITIONAL_RELATION'),
        subject=first['predicate'], object=last['predicate'], domain=first.get('domain') or 'UNKNOWN',
        quantifier=first.get('quantifier') or 'UNKNOWN', polarity=last.get('polarity') or 'UNKNOWN',
        modality='SYMBOLIC_EXECUTION' if operational else first['modality'], time=first.get('time') or 'UNKNOWN',
        stage=last['stage'], scope=first['scope'], source_hash=path[0]['source_hash'], edition=edition,
        assumptions=tuple(sorted({a for p in path for a in (p.get('assumptions') or [])})),**roles)


def rejected_joins(premises: list[dict]) -> list[dict]:
    from .contract import coordinate
    out = []
    for a in premises:
        for b in premises:
            if a['id']==b['id']:
                continue
            same_label = a['dst']['predicate']==b['src']['predicate']
            if same_label and (coordinate(a['dst'])!=coordinate(b['src']) or not composable([a,b])):
                out.append({'left_premise':a['id'],'right_premise':b['id'],
                    'source_refs':sorted(set(a['source_refs']+b['source_refs'])),
                    'status':'UNSUPPORTED_RELATION_SIGNATURE',
                    'reason':'Middle coordinate, guard, polarity, domain, quantifier, role, time or relation composition is incompatible.',
                    'left_role':a['dst'],'right_role':b['src']})
    return out
