"""Local owner registration of unchanged external NFA; never imported by MCP."""
from itertools import product
import hashlib
import json
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, PrivateFormat, NoEncryption
from normalizer import canonical, digest
from research_store import ResearchStore
from research_cycle009 import MECHANISM
from typed_cycle011 import ordinal_parameters
from typed_cycle011_store import register_scope
from engine017_store import register, content_material
from engine017_contract import SourceEnvelope017, source_identity
import beta019_source as source


def seed(database: Path, workspace: Path, seals: Path, case: int, stamp: str) -> dict:
    project = 'LM_QA_TYPED011_ENGINE017_BETA019_' + hashlib.sha256(stamp.encode()).hexdigest()[:16] + '_' + str(case)
    scoped = 'EXTERNAL019/' + project
    declared, observation = source.declaration(), None
    observation = source.acquisition(declared)
    mode = ('exact', 'exact', 'withheld_sensor', 'instrument_error')[case]
    target = [1] if case == 1 else []
    environment = {'project': project, 'declaration': declared, 'target_word': target, 'mode': mode, 'salt': digest({'project': project, 'case': case})}
    seals.mkdir(mode=0o700, exist_ok=True)
    seal, key_file = seals / (project + '.json'), seals / (project + '.ed25519')
    with seal.open('x') as stream:
        stream.write(canonical(environment))
    seal.chmod(0o600)
    key = Ed25519PrivateKey.generate()
    with key_file.open('xb') as stream:
        stream.write(key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption()))
    key_file.chmod(0o600)
    store = ResearchStore(database)
    def record(label, body, parent=None):
        event = store.record(project, 'hypothesis', label, canonical({'scope': scoped, 'version': 1, **body}),
            'hypothesis', parent_id=parent, request_key=project + ':' + label)
        with store._connect() as c:
            return dict(c.execute('SELECT * FROM events WHERE id=?', (event['id'],)).fetchone())
    identity = digest({'object': source.OBJECT, 'commit': source.COMMIT, 'native': source.definition_sha()})
    fixture = record('source-commitment', {'claim_type': 'SOURCE_CLAIM', 'fixture_sha256': identity,
        'environment_commitment': hashlib.sha256(seal.read_bytes()).hexdigest(), 'source_origin': 'public automata-lib NFA example, MIT'})
    native = record('upstream-object', {'claim_type': 'SOURCE_CLAIM', 'object': source.OBJECT, 'upstream_commit': source.COMMIT, 'license': 'MIT'})
    observed = record('native-acquisition', {'claim_type': 'SOURCE_CLAIM', **observation}, native['id'])
    actions, histories, hypotheses = source.OBJECT['input_symbols'], [], []
    for i, word in enumerate(declared['discrimination_histories']):
        event = record('history-' + str(i), {'claim_type': 'HYPOTHESIS', 'word': [actions[a] for a in word]}, native['id'])
        ref = 'event:' + str(event['id']); histories.append(ref)
        hypotheses.append({'id': ref, 'ref': ref, 'weight': 1, 'predictive': True, 'question': 'current', 'depends_on': []})
    independent = record('independent-provenance', {'claim_type': 'HYPOTHESIS', 'scope': 'independent', 'word': []}, native['id'])
    independent_ref = 'event:' + str(independent['id'])
    hypotheses.append({'id': 'IND', 'ref': independent_ref, 'weight': 1, 'predictive': False, 'question': 'independent', 'depends_on': []})
    tests = [{'id': 't' + str(i), 'ordinal': i, 'suffix': list(w), 'cost': len(w) - 1}
        for i, w in enumerate(w for n in (1, 2) for w in product(actions, repeat=n))]
    domain = [{'id': 'v' + str(i), 'ordinal': i, 'word': list(w), 'cost': len(w)}
        for i, w in enumerate(w for n in (1, 2, 3, 4) for w in product(range(2), repeat=n))]
    spec = {'parameters': {**declared, 'actions': actions}, 'histories': histories, 'independent_ref': independent_ref,
        'tests': tests, 'validation_domain': domain, 'hypotheses': hypotheses, 'current_observation': 0,
        'known_failures': [], 'unknowns': ['Actual current history is withheld; source formula is public; no discovery claim.'],
        'observer': source.OBSERVER, 'scope': scoped, 'version': 1, 'primitive_sha256': source.definition_sha()}
    root = record('source-root', {'claim_type': 'HYPOTHESIS', 'source_event_id': native['id'],
        'observations_event_id': observed['id'], 'source_spec': spec}, native['id'])
    imported = store.frontier.import_history({'import_key': project + ':scope', 'project': project,
        'sources': [{'id': fixture['id'], 'sha256': digest(fixture)}],
        'obligations': [{'key': 'external019', 'statement': 'Bounded observation of original external NFA; no proof authority.',
            'scope': scoped, 'source_event_ids': [fixture['id'], root['id']], 'evidence_refs': ['event:' + str(native['id'])]}],
        'constraints': [{'kind': 'allowed_experiment', 'obligation_key': 'external019', 'mechanisms': [MECHANISM], 'scope': scoped,
            'source_event_ids': [fixture['id']], 'source_representations': ['fixture009:' + identity],
            'reason': 'Exact external NFA, original a/b operations, bounded source-defined words, explicit local owner activation.',
            'reopen_conditions': ['New owner review/version and evidence.']}]}, '019 task-authorized private QA operator')
    artifacts = workspace / 'artifacts' / project; artifacts.mkdir(parents=True)
    manifest = SourceEnvelope017(source_id='automata-lib9.2.0-public-nfa', project=project, scope=scoped, version=1,
        origin_sha256=digest({'object': source.OBJECT, 'commit': source.COMMIT}), content_sha256=digest(content_material(spec, observation)),
        native_definition_sha256=source.definition_sha(), operation_definition_sha256=digest(ordinal_parameters(spec['parameters'])),
        operations=[{'ordinal': i, 'name': a, 'definition_sha256': source.definition_sha()} for i, a in enumerate(actions)], observer=source.OBSERVER,
        rights='MIT; original Copyright (c)2016-2025 Caleb Evans retained with raw source.',
        provenance=['https://github.com/caleb531/automata/tree/' + source.COMMIT, 'docs/examples/fa-examples.md original my_nfa, ast.literal_eval extraction'],
        unknowns=['No physical authentication, universal proof, autonomous discovery or structural advantage claim.'], inspection_status='COMPUTABLE_CHECKED').model_dump()
    executor_sha = hashlib.sha256(Path(__file__).with_name('beta019_executor.py').read_bytes()).hexdigest()
    register_scope(database, project, {'scope': scoped, 'fixture_id': fixture['id'], 'fixture_sha256': digest(fixture),
        'fixture_content_sha256': identity, 'source_family_id': source_identity(manifest), 'operation_definition_sha256': manifest['operation_definition_sha256'],
        'native_definition_sha256': source.definition_sha(), 'executor_code_sha256': executor_sha,
        'environment_sha256': hashlib.sha256(seal.read_bytes()).hexdigest(), 'artifact_directory': str(artifacts)})
    binding = {'root_event_id': root['id'], 'obligation_id': imported['obligation_ids']['external019'], 'source_identity': source_identity(manifest),
        'executor_public_key': key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex(), 'executor_sha256': executor_sha,
        'measurement_code_sha256': hashlib.sha256(Path(source.__file__).read_bytes()).hexdigest()}
    registration = register(database, manifest, binding)
    return {'project': project, 'case': case, 'manifest': manifest, 'registration': registration, 'fixture_id': fixture['id'],
        'root_id': root['id'], 'obligation_id': imported['obligation_ids']['external019'], 'environment': str(seal),
        'private_key_file': str(key_file), 'declaration': declared, 'mode': mode}
