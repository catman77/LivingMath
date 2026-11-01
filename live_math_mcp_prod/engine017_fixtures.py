"""Explicit owner provisioning for frozen017 acceptance; not imported by server."""
import hashlib
import json
from itertools import product
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, PrivateFormat, NoEncryption
from normalizer import canonical, digest
from research_store import ResearchStore
from research_cycle009 import MECHANISM
from typed_cycle011 import ordinal_parameters
from typed_cycle011_store import register_scope
from law_validation014_native import native_sha
from law_validation014_qa import acquisition, record
from engine017_contract import SourceEnvelope017, source_identity
from engine017_store import content_material, register

SOURCE = Path(__file__).resolve().parent
OBSERVER = {'projection': 'primary', 'mod': None}


def seed(database, workspace, seals, family, case, stamp):
    """Frozen declaration/target/sensor mode precede any controller proposal."""
    key = family['id'] + str(case['case'])
    project = 'LM_QA_TYPED011_ENGINE017_' + stamp[-12:] + '_' + key
    scoped = 'QA017/' + project
    declaration = {k: v for k, v in family.items() if k not in ('success_target', 'failure_target', 'validation_domain')}
    store = ResearchStore(database)
    observations = acquisition(declaration)
    environment = {'project': project, 'declaration': declaration, 'target_word': case['target_word'],
        'mode': case['mode'], 'salt': digest({'frozen-case': key, 'cohort': stamp})}
    seal = seals / (key + '.json')
    seal.write_text(canonical(environment))
    seal.chmod(0o600)
    env_sha = hashlib.sha256(seal.read_bytes()).hexdigest()
    key_file = seals / (key + '.ed25519')
    key_pair = Ed25519PrivateKey.generate()
    key_file.write_bytes(key_pair.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption()))
    key_file.chmod(0o600)
    identity = digest({'native': native_sha(), 'declaration': declaration, 'scope': scoped})
    fixture = record(store, project, 'operator-source-commitment', {'claim_type': 'SOURCE_CLAIM', 'scope': scoped, 'version': 1,
        'fixture_sha256': identity, 'environment_commitment': env_sha})
    source = record(store, project, 'native-source', {'claim_type': 'SOURCE_CLAIM', 'scope': scoped, 'version': 1,
        'declaration': declaration, 'native_sha': native_sha()})
    observed = record(store, project, 'native-observations', {'claim_type': 'SOURCE_CLAIM', 'scope': scoped, 'version': 1,
        **{k: observations[k] for k in ('origin', 'transitions', 'executed_words')}}, source['id'])
    actions = ['a' + str(i) for i in range(declaration['arity'])]
    hypotheses, histories = [], []
    for index, word in enumerate(declaration['discrimination_histories']):
        h = record(store, project, 'source-history-' + str(index), {'claim_type': 'HYPOTHESIS', 'scope': scoped,
            'version': 1, 'word': [actions[a] for a in word]}, source['id'])
        ref = 'event:' + str(h['id'])
        histories.append(ref)
        hypotheses.append({'id': ref, 'ref': ref, 'weight': 1, 'predictive': True, 'question': 'current', 'depends_on': []})
    independent = record(store, project, 'independent-branch', {'claim_type': 'HYPOTHESIS', 'scope': 'independent',
        'version': 1, 'word': []}, source['id'])
    independent_ref = 'event:' + str(independent['id'])
    hypotheses.append({'id': 'IND', 'ref': independent_ref, 'weight': 1, 'predictive': False, 'question': 'independent', 'depends_on': []})
    tests = [{'id': 't' + str(i), 'ordinal': i, 'suffix': list(w), 'cost': len(w) - 1}
        for i, w in enumerate(w for n in (1, 2) for w in product(actions, repeat=n))]
    domain = [{'id': 'v' + str(i), 'ordinal': i, 'word': word, 'cost': len(word)} for i, word in enumerate(family['validation_domain'])]
    spec = {'parameters': {**declaration, 'actions': actions}, 'histories': histories, 'independent_ref': independent_ref,
        'tests': tests, 'validation_domain': domain, 'hypotheses': hypotheses, 'current_observation': 0,
        'known_failures': [], 'unknowns': ['Finite native acceptance source; no universal law or physical authenticity.'],
        'observer': OBSERVER, 'scope': scoped, 'version': 1, 'primitive_sha256': native_sha()}
    root = record(store, project, 'source-root', {'claim_type': 'HYPOTHESIS', 'scope': scoped, 'version': 1,
        'source_event_id': source['id'], 'observations_event_id': observed['id'], 'source_spec': spec}, source['id'])
    imported = store.frontier.import_history({'import_key': project + ':scope', 'project': project,
        'sources': [{'id': fixture['id'], 'sha256': digest(fixture)}],
        'obligations': [{'key': 'engine', 'statement': 'Bounded native017 staging research; no proof or model activation.',
            'scope': scoped, 'source_event_ids': [fixture['id'], root['id']], 'evidence_refs': ['event:' + str(source['id'])]}],
        'constraints': [{'kind': 'allowed_experiment', 'obligation_key': 'engine', 'mechanisms': [MECHANISM],
            'scope': scoped, 'source_event_ids': [fixture['id']], 'source_representations': ['fixture009:' + identity],
            'reason': 'Only exact native source, current typed binding, ordered word and owner activation.',
            'reopen_conditions': ['New source contract/evidence and explicit operator review.']}]}, 'User-authorized017 staging operator')
    directory = workspace / 'artifacts' / key
    directory.mkdir(parents=True)
    manifest = SourceEnvelope017(source_id='native017-' + key, project=project, scope=scoped, version=1,
        origin_sha256=digest({'native': native_sha(), 'declaration': declaration}), content_sha256=digest(content_material(spec, json.loads(observed['content']))),
        native_definition_sha256=native_sha(), operation_definition_sha256=digest(ordinal_parameters(spec['parameters'])),
        operations=[{'ordinal': i, 'name': action, 'definition_sha256': native_sha()} for i, action in enumerate(actions)],
        observer=OBSERVER, rights='Local user-authorized staging computational source and generated receipts.',
        provenance=['Frozen017 preregistration', 'Unchanged reviewed source014 native implementation'],
        unknowns=['No physical authentication or mathematical proof claim.'], inspection_status='COMPUTABLE_CHECKED').model_dump()
    source_id = source_identity(manifest)
    register_scope(database, project, {'scope': scoped, 'fixture_id': fixture['id'], 'fixture_sha256': digest(fixture),
        'fixture_content_sha256': identity, 'source_family_id': source_id, 'operation_definition_sha256': manifest['operation_definition_sha256'],
        'native_definition_sha256': native_sha(), 'executor_code_sha256': hashlib.sha256((SOURCE / 'engine017_executor.py').read_bytes()).hexdigest(),
        'environment_sha256': env_sha, 'artifact_directory': str(directory)})
    binding = {'root_event_id': root['id'], 'obligation_id': imported['obligation_ids']['engine'],
        'source_identity': source_id, 'executor_public_key': key_pair.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex(),
        'executor_sha256': hashlib.sha256((SOURCE / 'engine017_executor.py').read_bytes()).hexdigest(),
        'measurement_code_sha256': hashlib.sha256((SOURCE / 'engine017_measurement.py').read_bytes()).hexdigest()}
    registration = register(database, manifest, binding)
    return {'key': key, 'family': family['id'], 'case': case['case'], 'project': project, 'manifest': manifest,
        'registration': registration, 'obligation_id': imported['obligation_ids']['engine'], 'root_id': root['id'],
        'fixture_id': fixture['id'], 'environment': str(seal), 'private_key_file': str(key_file), 'declaration': declaration,
        'expected': case['expected']}
