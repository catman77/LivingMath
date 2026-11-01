"""External-source acceptance with original NFA, not the old QA algebras."""
import copy
from itertools import product
import json
from pathlib import Path
import sqlite3

import pytest
from normalizer import digest
from research_store import ResearchStore
from typed_cycle011_store import install as install011
from engine017_store import install as install017
from deploy018_storage import migrate
from deploy018_authority import install, activate, reconcile
from beta019_seed import seed
from beta019_controller import Controller019
from beta019_executor import execute
from beta019_receipt import Receipt019
from beta019_operator import commit
from operational013 import LinearTransport
from qa_positive_acceptance import snapshot
from test_engine017 import context as legacy_context
import beta019_source as source


@pytest.fixture
def context019(tmp_path):
    workspace, seals = tmp_path / 'workspace', tmp_path / 'seals'
    workspace.mkdir(); seals.mkdir()
    canonical, db = workspace / 'research.sqlite3', workspace / 'beta.sqlite3'
    ResearchStore(canonical); ResearchStore(db)
    install011(db, canonical); install017(db); migrate(canonical); migrate(db); install(db)
    return db, workspace, seals


def registered(context, case=0, stamp='UNIT019'):
    db, workspace, seals = context
    return db, seed(db, workspace, seals, case, stamp)


def measurement(context, case=0):
    db, world = registered(context, case)
    controller = Controller019(db)
    pc = controller.precommit({'project': world['project']}, 'unit')
    activate(db, world['project'], pc['move_id'], 'unit')
    value = execute(db, world['project'], pc['move_id'], world['environment'], world['private_key_file'])
    env = value['envelope']
    request = {'project': world['project'], 'move_id': pc['move_id'], 'event_id': value['event_id'], 'request_key': 'commit',
        **{k: env[k] for k in ('outcome', 'observed', 'summary', 'reason', 'proof_status')}}
    return db, world, pc, value, request


def test_original_nfa_operations_and_fixed_embedding_agree_on_finite_domain():
    from automata.fa.nfa import NFA
    declared = source.declaration(); data = source.OBJECT
    native = NFA(states=set(data['states']), input_symbols=set(data['input_symbols']),
        transitions={q: {a: set(v) for a, v in row.items()} for q, row in data['transitions'].items()},
        initial_state=data['initial_state'], final_states=set(data['final_states']))
    observed = source.acquisition(declared)
    law = LinearTransport.fit(observed['origin'], observed['transitions'], {'source': source.definition_sha()})
    assert law.status == 'CANDIDATE_TRANSPORT'
    for word in (list(w) for n in range(5) for w in product(range(2), repeat=n)):
        image = observed['origin']
        for action in word:
            image = law.step(image, action)
        actual = source.native_trace(word)[-1]
        assert image == source.encode(actual)
        value = source.Port(declared).observe_image(image, source.OBSERVER)
        assert bool(value) == native.accepts_input(''.join(data['input_symbols'][a] for a in word))


def test_coordinate_identity_is_distinct_from_observer_equality():
    a, b = source.encode(['q0']), source.encode([])
    port = source.Port(source.declaration())
    assert a != b
    assert port.observe_image(a, source.OBSERVER) == port.observe_image(b, source.OBSERVER) == 0
    changed = copy.deepcopy(source.declaration()); changed['source_object']['initial_state'] = 'q1'
    with pytest.raises(ValueError, match='UNSUPPORTED_SOURCE_DEFINITION'):
        source.Port(changed)


def test_cohort_control_names_are_distinct_safe_identifiers(context019):
    db, workspace, seals = context019
    first = seed(db, workspace, seals, 0, 'cohort-1:stale_version')
    second = seed(db, workspace, seals, 0, 'cohort-2:stale_version')
    assert first['project'] != second['project'] and ':' not in first['project']
    assert Path(first['private_key_file']).read_bytes() != Path(second['private_key_file']).read_bytes()
    with pytest.raises(FileExistsError):
        seed(db, workspace, seals, 0, 'cohort-1:stale_version')


def test_reviewed_router_retains_original017_native_profile(legacy_context):
    from engine017_fixtures import seed as legacy_seed
    from beta019_http import ReviewedRouter
    policy, _, db, workspace, seals = legacy_context
    world = legacy_seed(db, workspace, seals, policy['families'][0], policy['cases'][0], 'ROUTER019')
    out = ReviewedRouter(db).preview({'project': world['project']})
    assert out['status'] == 'PROPOSAL_READY' and out['controller_version'] == '017.1'
    assert not out['execution_permission']['allowed']


def test_proposal_is_source_owned_alias_invariant_and_does_not_grant(context019):
    db, world = registered(context019)
    c = Controller019(db)
    out = c.preview({'project': world['project']})
    assert out['status'] == 'PROPOSAL_READY', out
    assert not any(row['operation'] == 'E' for row in out['native_trace'])
    assert out['claim_fingerprint'] == c.preview({'project': world['project'], 'display_label': 'alias'})['claim_fingerprint']
    pc = c.precommit({'project': world['project']}, 'stable')
    before = snapshot(db)
    assert c.precommit({'project': world['project'], 'display_label': 'renamed'}, 'stable') == pc
    assert snapshot(db) == before
    assert not pc['execution_permission']['allowed']
    with pytest.raises(ValueError, match='NO_TYPED_ACTIVATION'):
        execute(db, world['project'], pc['move_id'], '/must-not-open', '/must-not-open')
    assert snapshot(db) == before
    with pytest.raises(ValueError, match='PRECOMMIT_KEY_CONFLICT'):
        c.precommit({'project': world['project'], 'version': 2}, 'stable')


@pytest.mark.parametrize('case', range(4))
def test_four_outcomes_are_bound_to_native_attempt_not_prediction(context019, case):
    db, world, pc, value, request = measurement(context019, case)
    checked = Receipt019(db).validate(world['project'], pc['move_id'], value['event_id'])
    assert checked['status'] == 'VALID_BOUND_MEASUREMENT', checked
    assert checked['signature_verified'] and checked['lease018_verified']
    env = value['envelope']
    assert env['outcome'] == ['SUCCESS', 'FAILURE', 'INCONCLUSIVE', 'ERROR'][case]
    result = commit(db, request)
    assert result['status'] == 'COMPLETED' and not result['execution_permission']['allowed']
    before = snapshot(db)
    assert commit(db, request)['idempotent']
    assert snapshot(db) == before
    with pytest.raises(ValueError, match='CONFLICT'):
        commit(db, {**request, 'outcome': 'ERROR' if case != 3 else 'SUCCESS'})
    assert snapshot(db) == before
    with pytest.raises(ValueError, match='TERMINAL_OR_REVOKED_ACTIVATION'):
        activate(db, world['project'], pc['move_id'], 'reactivate')
    next_state = Controller019(db).preview({'project': world['project'], 'known_fingerprints': [], 'latest_feedback': None})
    if case < 2:
        assert next_state['status'] == 'PROPOSAL_READY' and next_state['purpose'] == 'VALIDATE_TRANSFER', next_state
    else:
        assert next_state['status'] == ('AWAITING_INCONCLUSIVE_EVIDENCE' if case == 2 else 'ERROR_REQUIRES_OPERATOR_REVIEW')
    assert all(e['status'] != 'verified' for e in ResearchStore(db).events(world['project'], 100))


@pytest.mark.parametrize('change', ['signature', 'nonce', 'key_id', 'project', 'expiry'])
def test_attestation_tamper_denied_with_exact_reason_and_no_delta(context019, change):
    db, world, pc, value, request = measurement(context019)
    with sqlite3.connect(db) as c:
        if change == 'expiry':
            c.execute('DROP TRIGGER lm018_deploy018_leases_update')
            c.execute('UPDATE deploy018_leases SET expires=0')
        else:
            c.execute('DROP TRIGGER lm018_deploy018_attestations_update')
            body = json.loads(c.execute('SELECT payload_json FROM deploy018_attestations').fetchone()[0])
            if change == 'signature':
                body['signature'] = '00' * 64
            else:
                body['body']['lease'][change] = 'adversarial'
            c.execute('UPDATE deploy018_attestations SET payload_json=?', (json.dumps(body),))
    before = snapshot(db)
    rejected = Receipt019(db).validate(world['project'], pc['move_id'], value['event_id'])
    expected = '019_ATTESTATION_SIGNATURE_INVALID' if change == 'signature' else '018_LEASE_EXPIRED' if change == 'expiry' else '019_NONCE_OR_ATTESTATION_REBIND'
    assert rejected['status'] == 'REJECTED' and expected in rejected['reason'], rejected
    with pytest.raises(ValueError):
        commit(db, request)
    assert snapshot(db) == before


def test_stale_permission_and_foreign_event_do_not_read_keys_or_commit(context019):
    db, world, pc, value, request = measurement(context019)
    foreign = Receipt019(db).validate(world['project'] + '_OTHER', pc['move_id'], value['event_id'])
    assert foreign['status'] == 'REJECTED' and foreign['reason'] == 'MISSING_OR_FOREIGN_EVENT'
    current = ResearchStore(db).frontier.history(world['obligation_id'])[-1]
    ResearchStore(db).frontier.update(world['obligation_id'], current['version'], {'statement': current['statement'] + ' Reviewed next version.'})
    before = snapshot(db)
    with pytest.raises(ValueError, match='STALE_OBLIGATION_VERSION'):
        commit(db, request)
    assert snapshot(db) == before
    reconcile(db)
    assert not ResearchStore(db).moves.inspect(world['project'], pc['move_id'])['execution_permission']['allowed']


@pytest.mark.parametrize('query', [{'context_level': 'C4'}, {'observer': {'projection': 'primary', 'mod': 2}}, {'version': 2}, {'source_id': 'forged'}])
def test_missing_sufficiency_and_rebinding_fail_closed(context019, query):
    db, world = registered(context019)
    before = snapshot(db)
    value = Controller019(db).preview({'project': world['project'], **query})
    assert value['status'] == 'INSUFFICIENT_CONTEXT' and not value['execution_permission']['allowed']
    assert snapshot(db) == before
