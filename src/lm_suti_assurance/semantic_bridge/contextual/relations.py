"""Exact certified relations followed by fair shared finite-model investigation."""
from ...core import digest, canonical
from ...formal_bridge import fol
from ...formal_bridge.ir import Budget, Bound, limits
from .alpha import prove_alpha
from .proofs import prove_entailment
from .finite import FiniteModelCursor
from .resources import PairWork, PairBound


class Work:
    def __init__(self,budget):
        self.bounds=limits({k:v for k,v in budget.items() if k in ('max_models','max_cpu_ms','max_steps')});self.counter=Budget(self.bounds);self.models=0
    def tick(self,n=1):self.counter.tick(n)
    def remaining(self):
        import time
        self.tick();b=dict(self.bounds);b['max_steps']=max(1,b['max_steps']-self.counter.steps);b['max_cpu_ms']=max(1,int(b['max_cpu_ms']-(time.process_time()-self.counter.started)*1000));return b
    def evaluate(self,formula,signature,model):
        bounds=self.remaining();v=fol.evaluate(formula,signature,model,bounds)
        if v['status']=='UNKNOWN_BOUND':
            self.counter.steps+=bounds['max_steps']
            raise Bound('FORMULA_EVALUATION_BOUND')
        self.tick(v.get('evaluated_nodes',1));return v


def scenario(hypothesis,signature,model,work):
    f=work.evaluate(hypothesis['formula_ast'],signature,model) if 'formula_ast' in hypothesis else {'status':'ILL_TYPED','truth':None}
    assumptions=[]
    for assumption in hypothesis['assumptions']:
        value=work.evaluate(assumption,signature,model)
        if value['status']=='ILL_TYPED':value={'status':'UNKNOWN','truth':None,'reason':'ILL_TYPED_ASSUMPTION','typecheck':value['typecheck'],'execution_permission':False}
        assumptions.append(value)
    statuses=[x['status'] for x in assumptions]
    applicability='CONTEXT_INCOMPATIBLE' if 'FALSE' in statuses else 'UNKNOWN_CONTEXT' if any(x!='TRUE' for x in statuses) else 'APPLICABLE'
    obligations=[]
    for o in hypothesis['obligations']:
        v={**o,'status':'OPEN'}
        if 'assumption_ast' in o:v['formal_assumption_check']=work.evaluate(o['assumption_ast'],signature,model)
        obligations.append(v)
    return {'hypothesis_ref':hypothesis['hypothesis_ref'],'client_id':hypothesis['client_id'],'formula_truth':f['status'] if f['status'] in ('TRUE','FALSE','ILL_TYPED') else 'UNKNOWN','formula_evaluation':f,'assumption_truths':assumptions,'applicability':applicability,'assumption_scope':'DECLARED_ASSUMPTIONS' if assumptions else 'NO_DECLARED_ASSUMPTIONS','source_alignment_status':'LANGUAGE_INSUFFICIENT' if hypothesis['type_status']=='LANGUAGE_INSUFFICIENT' else 'PROPOSED','obligations':obligations,'execution_permission':False}


PROVED = {'PROVED_ENTAILMENT', 'PROVED_ALPHA_EQ'}
COUNTEREXAMPLES = {'COUNTERMODEL_A_NOT_B', 'COUNTERMODEL_B_NOT_A'}
DIRECTIONS = ('A_IMPLIES_B', 'B_IMPLIES_A')


def _decided(direction):
    return direction['status'] in PROVED | COUNTEREXAMPLES


def _edge(left, right):
    return {'left_ref': left['hypothesis_ref'], 'right_ref': right['hypothesis_ref'],
            'client_ids': [left['client_id'], right['client_id']], 'source_alignment_status': 'PROPOSED',
            'comparison_scope': 'ALL_CANDIDATE_ASSUMPTIONS_HOLD', 'context_applicability': 'UNKNOWN_CONTEXT',
            'proof_scope': 'FORMULAS_ONLY_ASSUMPTIONS_RETAINED_SEPARATELY', 'formal_contrast_calls': 0,
            'model_enumerations': 0, 'countermodels': [], 'proof_phase_completed': False,
            'directions': {k: {'status': 'UNKNOWN_BOUND', 'models_checked': 0, 'model_enumerations': 0,
                               'proof_kind': None, 'counterexample_ref': None, 'halt_reason': 'PROOF_NOT_STARTED'}
                           for k in DIRECTIONS}, 'execution_permission': False}


def _prepare(edge, left, right, signature, budget, work):
    work.tick()
    if any(h['type_status'] != 'TYPED' for h in (left, right)):
        edge['type_rejected'] = True
        for d in edge['directions'].values():
            d.update(status='TYPE_REJECTED', halt_reason='UNTYPED_OR_UNSUPPORTED_CANDIDATE')
        edge['proof_phase_completed'] = True
        return
    a, b = left['formula_ast'], right['formula_ast']
    edge['alpha'] = prove_alpha(a, b, signature)
    entries = [('A_IMPLIES_B', a, b, left['hypothesis_ref']), ('B_IMPLIES_A', b, a, right['hypothesis_ref'])]
    for key, x, y, _ in sorted(entries, key=lambda row: row[3]):
        if edge['alpha']['status'] == 'PROVED_ALPHA_EQ':
            proof = prove_alpha(x, y, signature)
            proof.update(proof_kind='ALPHA_NORMALIZATION', proof_rule='ALPHA_NORMALIZATION', models_checked=0, halt_reason=None)
        else:
            proof = prove_entailment(x, y, signature, budget.get('max_atoms', 10), work)
        edge['directions'][key].update(proof)
    edge['proof_phase_completed'] = True


def _summarize(edge):
    values = list(edge['directions'].values())
    completed = sum(_decided(d) for d in values)
    edge['summary'] = {'requested': 2, 'completed': completed, 'undecided': 2 - completed,
                       'proved': sum(d['status'] in PROVED for d in values),
                       'counterexample_directions': sum(d['status'] in COUNTEREXAMPLES for d in values)}
    if edge.get('type_rejected'):
        edge['status'] = 'TYPE_REJECTED'
    elif edge.get('alpha', {}).get('status') == 'PROVED_ALPHA_EQ':
        edge['status'] = 'PROVED_ALPHA_EQ'
    elif all(d['status'] in PROVED for d in values):
        edge['status'] = 'PROVED_LOGICAL_EQ'
    elif any(d['status'] in PROVED for d in values):
        edge['status'] = 'PROVED_ENTAILMENT'
    elif len(edge['countermodels']) == 2:
        edge['status'] = 'INCOMPARABLE_PROVED_BY_TWO_COUNTERMODELS'
    elif edge['countermodels']:
        edge['status'] = edge['countermodels'][0]['status']
    else:
        edge['status'] = 'UNKNOWN_BOUND' if any(d['status'] == 'UNKNOWN_BOUND' for d in values) else 'FINITE_SAME_ON_BOUND'


def compare_pairs(pairs, signature, budget, work, scenario_cells=0):
    """Prepare proofs and fairly share worlds AND fuel; one pair cannot consume another's share."""
    jobs = [(_edge(a, b), a, b) for a, b in pairs]
    ordered = sorted(jobs, key=lambda j: tuple(sorted([j[1]['hypothesis_ref'], j[2]['hypothesis_ref']])))
    reserve = work.bounds['max_steps'] // (2 if scenario_cells else 8)
    steps = (work.bounds['max_steps'] - reserve) // max(1, len(jobs))
    cpu = (work.bounds['max_cpu_ms'] * (3 if scenario_cells else 7) // (4 if scenario_cells else 8)) // max(1, len(jobs))
    allocations = {id(e): PairWork(work, steps, cpu) for e, _, _ in jobs}
    stop_reason = None
    exhausted = False
    try:
        for edge, a, b in ordered:
            local = allocations[id(edge)]
            edge['resource_allocation'] = {'max_steps': steps, 'max_cpu_ms': cpu, 'scope': 'PAIR_PROOF_AND_SEARCH_SHARED_GLOBAL_CAP'}
            try:
                with local.active():
                    _prepare(edge, a, b, signature, budget, local)
            except PairBound as exc:
                edge['search_halt_reason'] = str(exc)
        cursor = FiniteModelCursor(signature)
        while True:
            active = [(e, a, b) for e, a, b in ordered if not e.get('type_rejected') and not e.get('search_halt_reason') and any(not _decided(d) for d in e['directions'].values())]
            if not active:
                break
            try:
                model = next(cursor)
            except StopIteration:
                exhausted = True
                stop_reason = 'FINITE_EXHAUSTED'
                break
            if work.models >= work.bounds['max_models']:
                stop_reason = 'TOTAL_MODEL_BOUND'
                break
            work.tick()
            model_touched = False
            cache = {}
            for edge, left, right in active:
                local = allocations[id(edge)]
                pair_touched = False
                def touch():
                    nonlocal model_touched, pair_touched
                    if not model_touched:
                        work.models += 1
                        model_touched = True
                    if not pair_touched:
                        edge['formal_contrast_calls'] = 1
                        edge['model_enumerations'] += 1
                        for direction in edge['directions'].values():
                            if not _decided(direction):
                                direction['models_checked'] += 1
                                direction['model_enumerations'] += 1
                        pair_touched = True
                local.before_evaluate = touch
                def evaluate(phi):
                    key = canonical(phi)
                    if key not in cache:
                        cache[key] = local.evaluate(phi, signature, model)
                    else:
                        local.tick()
                        touch()
                    return cache[key]
                try:
                    with local.active():
                        assumptions = [*left['assumptions'], *right['assumptions']]
                        context = [evaluate(p) for p in sorted(assumptions, key=canonical)]
                        if any(v['truth'] is not True for v in context):
                            continue
                        values = [evaluate(h['formula_ast'])['truth'] for h in [left, right]]
                        if any(type(v) is not bool for v in values):
                            raise PairBound('PAIR_MODEL_EVALUATION_UNKNOWN')
                        for key, expected, label in [('A_IMPLIES_B', [True, False], 'COUNTERMODEL_A_NOT_B'),
                                                     ('B_IMPLIES_A', [False, True], 'COUNTERMODEL_B_NOT_A')]:
                            direction = edge['directions'][key]
                            if _decided(direction) or values != expected:
                                continue
                            checks = [scenario(h, signature, model, local) for h in [left, right]]
                            if [c['formula_evaluation']['truth'] for c in checks] != expected or any(c['applicability'] != 'APPLICABLE' for c in checks):
                                raise ValueError('COUNTERMODEL_CHECK_REJECTED')
                            cm = {'status': label, 'model_ref': digest(model), 'model': model, 'model_sha256': digest(model),
                                  'origin': 'FORMAL_COUNTERMODEL', 'truth_vector': values, 'checks': checks,
                                  'comparison_scope': 'ALL_CANDIDATE_ASSUMPTIONS_HOLD', 'execution_permission': False}
                            edge['countermodels'].append(cm)
                            direction.update(status=label, proof_kind='FINITE_COUNTERMODEL', counterexample_ref=digest(model), halt_reason='COUNTERMODEL_FOUND')
                            direction['finite_search'] = {'status': 'FINITE_COUNTERMODEL', 'models_checked': direction['models_checked'], 'halt_reason': 'COUNTERMODEL_FOUND', 'equivalence_claim': False}
                except PairBound as exc:
                    edge['search_halt_reason'] = str(exc)
                finally:
                    local.before_evaluate = None
    except Bound as exc:
        stop_reason = str(exc)
    for edge, _, _ in jobs:
        edge['charged_steps'] = allocations[id(edge)].steps
        local_halt = edge.get('search_halt_reason')
        for d in edge['directions'].values():
            if not _decided(d) and d['status'] != 'TYPE_REJECTED':
                if d['status'] != 'UNKNOWN_BOUND':
                    d['proof_attempt'] = {'status': d['status'], 'reason': d.get('reason')}
                d.update(status='NO_COUNTERMODEL_WITHIN_BOUND' if exhausted and not local_halt else 'UNKNOWN_BOUND',
                         halt_reason=local_halt or stop_reason or 'PROOF_NOT_COMPLETED')
                d['finite_search'] = {'status': d['status'], 'models_checked': d['models_checked'], 'halt_reason': d['halt_reason'], 'equivalence_claim': False}
        _summarize(edge)
    if stop_reason is None and any(e.get('search_halt_reason') for e, _, _ in jobs):
        stop_reason = 'PAIR_LOCAL_BOUNDS'
    return [e for e, _, _ in jobs], stop_reason


def pair(left, right, signature, budget, work):
    """Compatibility wrapper for one pair; batch callers use compare_pairs."""
    return compare_pairs([(left, right)], signature, budget, work)[0][0]
