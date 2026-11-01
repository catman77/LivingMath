"""Deterministic synthetic fixtures only; all writes target explicit temporary DBs."""
import copy
import itertools
import json
from pathlib import Path
from unittest.mock import patch

from frontier import fingerprint_hash
from normalizer import read_history
from research_store import ResearchStore

SEED = 104004


def create_world(path: Path, index: int) -> dict:
    store = ResearchStore(path)
    project = 'LOCAL_N004_' + str(index)
    events = {}
    def event(key, statement, representation='point_value', scope='scope-A', kind='hypothesis', status='hypothesis', parent=None, **extra):
        payload = {'statement': statement, 'scope': scope, 'representation': representation, 'version': 1,
            'claim_type': 'COUNTEREXAMPLE' if kind == 'counterexample' else 'SOURCE_CLAIM',
            'surface_forms': ['zero' if key in {'point', 'germ', 'false_alias'} else key],
            'claim_map': {'source_claim': statement}, 'method_model': {'input': 'finite fixture', 'operation': 'read only', 'output': 'unverified observation'},
            'counter_reading': None, 'observables': ['point_value'], **extra}
        result = store.record(project, kind, 'zero' if key in {'point', 'germ', 'false_alias'} else key,
            json.dumps(payload, ensure_ascii=index % 2 == 0), status, parent_id=parent)
        events[key] = result['id']
        return result['id']
    with patch('time.time', return_value=1793100000 + index * 100):
        root = event('root', 'Two candidate finite continuations share a source; applicability remains scoped.')
        point = event('point', {'polynomial_coefficients': [0, 1], 'input': 0, 'value': 0}, parent=root)
        germ = event('germ', 'Pointwise zero does not establish a zero analytic germ.', representation='analytic_germ', parent=root,
                     relations=[{'type': 'requires_witness', 'target_ref': 'event:' + str(point)}], unknowns=['germ identity witness missing'])
        adverse = event('adverse', 'The scoped continuation failed a finite check.', kind='counterexample', status='refuted', parent=root,
                        relations=[{'type': 'contradicts', 'target_ref': 'event:' + str(root)}])
        prev = adverse
        for depth in range(2 + index % 3):
            prev = event('dependency_' + str(depth), 'Retain the dependency and its contrary evidence.', parent=prev,
                         premises=['event:' + str(prev)], relations=[{'type': 'depends_on', 'target_ref': 'event:' + str(prev)}])
        event('alias', 'A second source spelling; no substitution witness.', parent=root,
              relations=[{'type': 'alias_candidate', 'target_ref': 'event:' + str(point)}])
        event('false_alias', 'Same term, other representation and scope.', representation='analytic_germ', scope='scope-B', parent=root,
              relations=[{'type': 'alias_candidate', 'target_ref': 'event:' + str(germ)}])
        independent = event('independent', 'Independent branch remains available.', scope='scope-I', parent=root,
                            relations=[{'type': 'independent_of', 'target_ref': 'event:' + str(adverse)}])
        event('old_rule', 'Old version and scope are retained, not merged with current.', scope='scope-old', parent=root,
              version=0, epistemic_status='superseded')
        unknown_guard = event('unknown_guard', 'Applicability guard h is not yet measured.', parent=root,
                              claim_type='UNKNOWN', unknowns=['h in {0,1}; neither value established'])
        left = event('microtheory_left', 'Continuation L requires h=0.', parent=root, claim_type='HYPOTHESIS',
                     premises=['event:' + str(unknown_guard)])
        right = event('microtheory_right', 'Continuation R requires h=1.', parent=root, claim_type='HYPOTHESIS',
                      premises=['event:' + str(unknown_guard)])
        separating = event('separating_test', 'A bounded read of h distinguishes L from R.', parent=root,
                           method_model={'input': 'hidden h', 'operation': 'read h once', 'output': '0 or1, not given'})
        empty = event('empty_test', 'Reading an unrelated constant does not distinguish L from R.', parent=independent)
        opaque = store.record(project, 'interpretation', 'unparsed', 'Maybe an analytic continuation?\nNo witness or scope supplied.', 'hypothesis', parent_id=root)
        events['opaque'] = opaque['id']
        for n in range(8):
            event('unrelated_' + str(n), 'Explicitly separate scope. ' + ('source retained; ' * 70), scope='scope-unrelated')
        # A separate source is never imported into the project view.
        foreign = store.record(project + '_OTHER', 'hypothesis', 'zero', 'Foreign source; not a local alias witness.')
        with store._connect() as connection:
            row = dict(connection.execute('SELECT * FROM events WHERE id=?', (root,)).fetchone())
        obligations = []
        branches = {}
        for name, state, source, scope in [('active', 'OPEN', root, 'scope-A'), ('closed', 'REFUTED', adverse, 'scope-A'),
                                          ('open', 'OPEN', root, 'scope-new'), ('independent', 'OPEN', independent, 'scope-I')]:
            item = {'key': name, 'statement': 'Synthetic ' + name + ' branch; no truth claim.', 'scope': scope,
                'source_event_ids': [source], 'evidence_refs': ['event:' + str(source)], 'status': state}
            if state == 'REFUTED':
                item.update(closure_reason='Counterexample retained.', reopen_conditions=['New version and source-specific evidence.'])
            obligations.append(item)
        constraints = [{'kind': 'allowed_experiment', 'obligation_key': name, 'mechanisms': ['qa_normalization_' + name],
            'source_event_ids': [source], 'source_representations': ['point_value'], 'scope': scope,
            'reason': 'Synthetic bounded source read only.', 'reopen_conditions': ['Changed source requires review.']}
            for name, source, scope in [('active', root, 'scope-A'), ('independent', independent, 'scope-I')]]
        constraints.append({'kind': 'obsolete_mechanism', 'obligation_key': 'closed', 'mechanisms': ['qa_normalization_closed'],
            'source_event_ids': [adverse], 'reason': 'Counterexample retained.', 'reopen_conditions': ['New version and source-specific evidence.']})
        blueprint = {'project': project, 'import_key': project + ':synthetic', 'sources': [{'id': root, 'sha256': fingerprint_hash(row)}],
                     'obligations': obligations, 'constraints': constraints}
        imported = store.frontier.import_history(blueprint, 'SYNTHETIC_TEST_FIXTURE: not a live owner disposition')
        branches = imported['obligation_ids']
        candidates = []
        for branch, transform, has_adverse, diagnostic in itertools.product(branches, (False, True), (False, True), (False, True)):
            parent = independent if branch == 'independent' else root
            parents = [parent, prev]
            if has_adverse:
                parents.append(adverse)
            operation = {'mechanism': 'qa_normalization_' + branch, 'intent': 'transformation' if transform else 'experiment',
                'premises': ['Read the retained scoped source'], 'mathematical_properties': ['point_value'],
                'testable_consequence': 'One finite measurement with retained input address', 'required_evidence': ['Project-local finite source event']}
            move = {'active_frontier_id': branches[branch], 'parent_event_ids': parents,
                'proposed_operation': operation, 'source_representation': 'point_value',
                'target_representation': 'analytic_germ' if transform else 'point_value',
                'evidence_refs': ['event:' + str(e) for e in parents],
                'verification_plan': {'method': 'Read one finite item', 'failure_condition': 'Retained values disagree'}}
            if has_adverse and diagnostic:
                move['evidence_roles'] = {str(adverse): {'role': 'diagnostic_subject', 'reason': 'Study the failed observation, never assume it true.'}}
            candidates.append({'id': f'w{index}-{branch}-{int(transform)}-{int(has_adverse)}-{int(diagnostic)}',
                'project': project, 'proposal': 'Synthetic finite QA proposal', 'move': move,
                'oracle_parameters': {'branch': branch, 'transform': transform, 'adverse': has_adverse,
                                      'diagnostic': diagnostic, 'review_current': index % 2 == 0}})
        reviewed = next(a for a in candidates if a['oracle_parameters'] == {'branch': 'active', 'transform': False, 'adverse': True, 'diagnostic': True, 'review_current': index % 2 == 0})
        store.evidence_reviews.record(project, adverse, branches['active'], 1, reviewed['move']['proposed_operation'],
            'diagnostic_subject', 'SYNTHETIC external-review fixture; no production authority or mathematical proof.',
            ['event:' + str(root)], project + ':disposition', 'SYNTHETIC_TEST_OPERATOR')
        if index % 2:
            store.frontier.update(branches['active'], 1, {'status': 'TESTING'})
        historical = copy.deepcopy(next(a for a in candidates if a['oracle_parameters']['branch'] == 'active'
                                    and not a['oracle_parameters']['transform'] and not a['oracle_parameters']['adverse']))
        historical['move']['proposed_operation']['testable_consequence'] = 'Historical finite reading; completion is not a proof.'
        current_version = 2 if index % 2 else 1
        recorded = store.moves.record(project, {**historical['move'], 'active_frontier_version': current_version, 'scope': 'scope-A'}, project + ':historic-record')
        store.moves.audit(project, recorded['id'], project + ':historic-audit')
        store.moves.transition(project, recorded['id'], 'activate_experiment', project + ':historic-activate')
        store.moves.transition(project, recorded['id'], 'complete', project + ':historic-complete',
            ['event:' + str(root)], 'Synthetic software control only.', {'outcome': 'SUCCESS', 'summary': 'Synthetic finite control; no mathematical verification.'})
        historical['id'] = f'w{index}-historical-duplicate'
        historical['oracle_parameters']['historical_duplicate'] = True
        candidates.append(historical)
        transformation = copy.deepcopy(next(a for a in candidates if a['oracle_parameters']['branch'] == 'active'
                                        and a['oracle_parameters']['transform'] and not a['oracle_parameters']['adverse']))
        properties = ('point_value', 'analytic_function', 'observables', 'source_provenance', 'rule_applicability')
        contract = store.frontier.transformation_contract(project, 'point_value', transformation['move']['proposed_operation'], 'analytic_germ',
            {prop: {'statement': 'Synthetic ' + prop + ' declaration, not an established witness.', 'evidence_refs': ['event:' + str(point)]} for prop in properties}, [point])
        transformation['move']['transformation_contract_id'] = contract['id']
        transformation['id'] = f'w{index}-declared-contract-unproven'
        transformation['oracle_parameters']['contract'] = 'match'
        candidates.append(transformation)
        mismatch = copy.deepcopy(transformation)
        mismatch['id'] = f'w{index}-mismatched-contract'
        mismatch['move']['target_representation'] = 'another_germ_representation'
        mismatch['oracle_parameters']['contract'] = 'mismatch'
        candidates.append(mismatch)
        measurement = copy.deepcopy(next(a for a in candidates if a['oracle_parameters']['branch'] == 'active'
                                        and not a['oracle_parameters']['transform'] and not a['oracle_parameters']['adverse']))
        measurement['id'] = f'w{index}-hidden-guard-measurement'
        measurement['move']['parent_event_ids'] = [root, unknown_guard, left, right, separating, empty]
        measurement['move']['evidence_refs'] = ['event:' + str(e) for e in measurement['move']['parent_event_ids']]
        measurement['move']['proposed_operation']['testable_consequence'] = 'Measure h without asserting either competing continuation is established.'
        measurement['oracle_parameters']['measurement_control'] = True
        candidates.append(measurement)
    return {'index': index, 'project': project, 'events': events, 'foreign_event_id': foreign['id'],
            'branches': branches, 'candidates': candidates, 'history': read_history(path, project), 'database': str(path)}
