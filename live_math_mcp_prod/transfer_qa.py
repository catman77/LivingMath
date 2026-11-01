"""Bounded 003 experiment. No retries, no production patch and no LLM activation."""
import argparse
import asyncio
from datetime import datetime, timezone, timedelta
import hashlib
import json
import logging
from pathlib import Path
import random
import resource
import sqlite3
import subprocess
import sys
import time

import httpx
from mcp import ClientSession, types
from mcp.client.streamable_http import streamable_http_client

from attention_qa import configure, server_cpu
from frontier import fingerprint_hash
from qa_positive_acceptance import Acceptance, oauth, snapshot, write_json
from research_store import ResearchStore
from transfer_model import CONCURRENCY, MODEL, TIMEOUT, infer, prompt, schema
from transfer_oracle import LOSS, VERSION, active_origin, evaluate, exhaustive_check
from transfer_worlds import SEEDS, STATES, atoms, canonical_atoms, digest, render, world


class StopExperiment(RuntimeError):
    def __init__(self, classification: str, reason: str):
        super().__init__(reason)
        self.classification = classification


class Session(Acceptance):
    async def run(self, token: str) -> None:
        async with httpx.AsyncClient(headers={'Authorization': 'Bearer ' + token}, timeout=30,
            event_hooks={'request': [self.request_hook], 'response': [self.response_hook]}) as http:
            async with streamable_http_client(self.endpoint, http_client=http) as (read, write, _):
                async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=40),
                    client_info=types.Implementation(name='LM-MICROTHEORY-TRANSFER-003', version='1')) as session:
                    self.session = session
                    self.initialized = (await session.initialize()).model_dump(mode='json')
                    await self.work(self)


class Experiment:
    def __init__(self, base: Path, report: Path, config: dict, db: Path):
        self.base, self.report, self.config, self.db = base, report, config, db
        self.rows, self.failures, self.controls, self.bindings = [], [], [], {}
        self.stamp = base.name
        self.stage = 'initializing'
        self.start = time.monotonic()
        self.cpu_start = time.process_time()
        self.children_start = resource.getrusage(resource.RUSAGE_CHILDREN)
        self.server_start = server_cpu()

    def append(self, filename: str, item: dict) -> None:
        with (self.base / filename).open('a') as stream:
            stream.write(json.dumps(item, ensure_ascii=False) + '\n')

    def session(self, label: str, work) -> Session:
        # Fresh owner token per short serialized MCP phase; never held while waiting for inference.
        path = self.base / 'sessions' / label
        path.mkdir(parents=True, exist_ok=False)
        client = Session(path, self.db, self.config['LIVE_MATH_PUBLIC_URL'].rstrip('/'))
        client.work = work
        oauth(self.config, client)
        return client

    async def preflight(self, client: Session) -> None:
        tools = (await client.session.list_tools()).model_dump(mode='json')
        data = {'initialize': client.initialized, 'tools': tools,
            'health': await client.call('service_health', {}),
            'contract': await client.call('research_contract', {}),
            'rh_frontier': await client.call('research_frontier', {'project': 'RH', 'include_closed': True})}
        write_json(self.base / 'preflight.json', data)
        if data['health']['version'] != '0.4.2' or data['health']['schema_version'] != 5 or len(tools['tools']) != 18:
            raise StopExperiment('PROTOCOL_DEVIATION', 'Expected actual v0.4.2/schema5/18 tools')

    async def seed(self, client: Session, w: dict, suffix: str = '') -> dict:
        project = f'LM_QA_MT003_{self.stamp}_{w["index"]}_{w["repeat"]}{suffix}'
        bindings = {}
        for key in ('source', 'observation0', 'observation1', 'independent'):
            value = {'logical_ref': w['refs'][key], 'source_id': w['source_id'], 'provenance': 'operator_seeded'}
            if key == 'source':
                value['atoms'] = atoms(w, 0)
            elif key.startswith('observation'):
                s = 0 if key.endswith('0') else 15
                value.update(test_id=w['tests'][s], measured=w['theories'][0]['predictions'][s])
            else:
                value.update(branch_id=w['independent_id'], observed=sum(STATES[w['target']]))
            req = {'project': project, 'kind': 'experiment', 'status': 'experiment', 'focus': key,
                'result': json.dumps(value, sort_keys=True), 'request_key': project + ':' + key}
            if bindings:
                req['parent_id'] = bindings[w['refs']['source']]
            event = await client.call('record_result', req)
            bindings[w['refs'][key]] = event['id']
        source_id = bindings[w['refs']['source']]
        with ResearchStore(self.db)._connect() as connection:
            source_row = dict(connection.execute('SELECT * FROM events WHERE id=?', (source_id,)).fetchone())
        blueprint = {'project': project, 'import_key': project + ':frontier',
            'sources': [{'id': source_id, 'sha256': fingerprint_hash(source_row)}],
            'obligations': [{'key': 'measure', 'statement': 'Bounded read-only QA source measurement; no proof or transformation.',
                'scope': w['scope_id'], 'source_event_ids': [source_id], 'evidence_refs': ['event:' + str(source_id)], 'status': 'OPEN'}],
            'constraints': [{'kind': 'allowed_experiment', 'obligation_key': 'measure', 'mechanisms': [w['mechanism']],
                'source_event_ids': [source_id], 'source_representations': [w['representation']],
                'scope': w['scope_id'], 'reason': 'Preregistered exact QA source only; at most one finite item.',
                'reopen_conditions': ['Changed source or scope needs separate review.']}]}
        imported = ResearchStore(self.db).frontier.import_history(blueprint, 'User-authorized preregistered QA fixture, before inference')
        self.append('operator-imports.jsonl', {'request': blueprint, 'response': imported, 'origin': 'operator_seeded'})
        binding = {'project': project, 'events': bindings, 'obligation_id': imported['obligation_ids']['measure'], 'version': 1}
        self.bindings[(w['index'], w['repeat'], suffix)] = binding
        write_json(self.base / 'bindings.json', list(self.bindings.values()))
        return binding

    async def feedback(self, client: Session, w: dict, binding: dict) -> None:
        old = w['theories'][active_origin(w, w['target'], 0)]['predictions'][w['target']]
        measured = w['theories'][active_origin(w, w['target'], 1)]['predictions'][w['target']]
        assert old != measured
        event = await client.call('record_result', {'project': binding['project'], 'kind': 'counterexample',
            'status': 'experiment', 'focus': 'Precommitted environmental measurement correction',
            'result': json.dumps({'source_id': w['source_id'], 'context_version': 2,
                'environment_feature': w['features'][4], 'previous': 0, 'measured': 1,
                'physical_input': list(STATES[w['target']]), 'old_prediction': old, 'observed': measured,
                'independent_branch_unchanged': w['independent_id'], 'origin': 'compute/operator_precommitted'}),
            'parent_id': binding['events'][w['refs']['source']], 'request_key': binding['project'] + ':feedback'})
        binding['events'][w['refs']['feedback']] = event['id']
        updated = await client.call('research_obligation_update', {'project': binding['project'],
            'obligation_id': binding['obligation_id'], 'expected_version': 1, 'changes': {'status': 'TESTING'}})
        binding['version'] = updated['version']
        self.append('feedback.jsonl', {'project': binding['project'], 'event': event, 'origin': 'compute/operator_precommitted'})
        write_json(self.base / 'bindings.json', list(self.bindings.values()))

    def move(self, w: dict, binding: dict, a: dict) -> dict:
        refs = ['event:' + str(binding['events'].get(ref, 0)) for ref in a['evidence_refs']]
        parents = [binding['events'].get(ref, 0) for ref in a['evidence_refs']]
        representation = w['representation'] if a['source_id'] == w['source_id'] else 'unbound-source:' + a['source_id']
        return {'active_frontier_id': binding['obligation_id'], 'parent_event_ids': parents,
            'proposed_operation': {'mechanism': w['mechanism'], 'intent': 'experiment' if a['decision'] == 'propose_experiment' else 'review',
                'proof_claim': a['truth_claimed'],
                'premises': [a['critical_premise_id'] or 'Review requested; no premise established'],
                'mathematical_properties': [w['profile']], 'testable_consequence': json.dumps({
                    'theory_id': a['theory_id'], 'theory_version': a['theory_version'], 'test_id': a['test_id'],
                    'prediction': a['predicted_observation'], 'requested_scope': a['scope_id'], 'declared_source_version': a['source_version'],
                    'declared_context_version': a['context_version']}),
                'required_evidence': ['Project-local finite observation with retained source address']},
            'source_representation': representation, 'target_representation': representation,
            'evidence_refs': refs, 'verification_plan': {'method': 'Read the one declared finite source input.',
                                                       'failure_condition': json.dumps(a['falsifier'])}}

    async def audit(self, client: Session, w: dict, binding: dict, row: dict) -> None:
        move = self.move(w, binding, row['output'])
        response = await client.call('audit_research_shift', {'project': binding['project'],
            'proposal': row['output']['reason'], **move}, allow_error=True)
        if response and (response.get('execution_permission', {}).get('allowed') or response.get('proof_status') == 'verified'):
            raise StopExperiment('MCP_CORE_BUG', 'Advisory audit issued a grant or verified status')
        self.append('audits.jsonl', {'cell_id': row['id'], 'request': move, 'response': response,
            'proposal_quality_unchanged': row['metrics'], 'origin': 'server_advisory_only',
            'domain_limit': 'Server checks declared contract; it does not implement the finite microtheory oracle.'})

    def check(self, name: str, condition: bool) -> None:
        self.controls.append({'id': name, 'result': 'PASS' if condition else 'FAIL'})
        write_json(self.base / 'controls.json', self.controls)
        if not condition:
            raise StopExperiment('MCP_CORE_BUG', 'Deterministic control failed: ' + name)

    async def deterministic_controls(self, client: Session) -> None:
        from transfer_oracle import best_action
        w = world(0, 0)
        b = await self.seed(client, w, '_controls')
        move = {**self.move(w, b, best_action(w, 0)), 'scope': w['scope_id'], 'active_frontier_version': 1}
        project = b['project']
        recorded = await client.call('record_research_move', {'project': project, 'move': move, 'request_key': project + ':record'})
        mid = recorded['id']
        self.check('D01_proposal_is_not_permission', recorded['history'][0]['status'] == 'PROPOSED' and not recorded['execution_permission']['allowed'])
        again = await client.call('record_research_move', {'project': project, 'move': move, 'request_key': project + ':record'})
        self.check('D02_idempotent_record', again['id'] == mid and again['idempotent'])
        advisory = {k: v for k, v in move.items() if k not in {'scope', 'active_frontier_version'}}
        foreign = await client.call('record_result', {'project': project + '_other', 'kind': 'experiment', 'focus': 'Foreign QA source', 'result': 'Bounded QA only', 'status': 'experiment', 'request_key': project + ':foreign'})
        bad = {**advisory, 'parent_event_ids': [foreign['id']], 'evidence_refs': ['event:' + str(foreign['id'])]}
        response = await client.call('audit_research_shift', {'project': project, **bad}, allow_error=True)
        self.check('D03_foreign_source_rejected', response is None or response['verdict'] != 'EXPERIMENT_ALLOWED')
        response = await client.call('audit_research_shift', {'project': project, **advisory, 'target_representation': 'another_representation'})
        self.check('D04_representation_mismatch_reviewed', response['verdict'] != 'EXPERIMENT_ALLOWED')
        audited = await client.call('audit_research_move', {'project': project, 'move_id': mid, 'request_key': project + ':audit'})
        self.check('D05_audit_is_not_permission', audited['status'] == 'AUDITED' and not audited['execution_permission']['allowed'])
        allowed = await client.call('transition_research_move', {'project': project, 'move_id': mid, 'action': 'activate_experiment', 'request_key': project + ':activate'})
        self.check('D06_scoped_control_allowed', allowed['execution_permission']['allowed'])
        rejected = await client.call('transition_research_move', {'project': project, 'move_id': mid, 'action': 'complete',
            'reason': 'Missing result control', 'evidence_refs': ['event:' + str(b['events'][w['refs']['source']])], 'request_key': project + ':empty'}, allow_error=True)
        self.check('D07_complete_requires_result', rejected is None)
        complete = await client.call('transition_research_move', {'project': project, 'move_id': mid, 'action': 'complete',
            'reason': 'Deterministic QA lifecycle, not a scientific discovery.', 'evidence_refs': ['event:' + str(b['events'][w['refs']['source']])],
            'result': {'outcome': 'INCONCLUSIVE', 'summary': 'Finite software QA control completed, no truth established.'}, 'request_key': project + ':complete'})
        self.check('D08_completed_unverified_no_grant', complete['status'] == 'COMPLETED' and complete['proof_status'] == 'unverified' and not complete['execution_permission']['allowed'])
        reactivate = await client.call('transition_research_move', {'project': project, 'move_id': mid, 'action': 'activate_experiment', 'request_key': project + ':again'}, allow_error=True)
        self.check('D09_completed_cannot_reactivate', reactivate is None)
        # A different structured consequence is a separate control, never a cosmetic duplicate.
        second = json.loads(json.dumps(move));second['proposed_operation']['testable_consequence'] = 'Independent version-revocation control'
        rec = await client.call('record_research_move', {'project': project, 'move': second, 'request_key': project + ':second'})
        await client.call('audit_research_move', {'project': project, 'move_id': rec['id'], 'request_key': project + ':second-audit'})
        await client.call('transition_research_move', {'project': project, 'move_id': rec['id'], 'action': 'activate_experiment', 'request_key': project + ':second-activate'})
        await client.call('research_obligation_update', {'project': project, 'obligation_id': b['obligation_id'], 'expected_version': 1, 'changes': {'status': 'TESTING'}})
        inspected = await client.call('research_move_history', {'project': project, 'move_id': rec['id']})
        self.check('D10_version_change_revokes_permission', not inspected['execution_permission']['allowed'])
        await client.call('transition_research_move', {'project': project, 'move_id': rec['id'], 'action': 'abandon', 'reason': 'Version-revocation QA finished.', 'request_key': project + ':abandon'})

    async def cells(self, phase: str, index: int, repeat: int, time_index: int) -> list:
        semaphore = asyncio.Semaphore(CONCURRENCY)
        modes = ['F', 'S']
        random.Random(SEEDS[repeat] + index + time_index).shuffle(modes)
        async def one(mode):
            cell = {'phase': phase, 'world': index, 'repeat': repeat, 'time': time_index, 'mode': mode}
            label = 'c' + digest(cell)[:20]
            filename = self.base / 'frozen-prompts' / (label + '.txt')
            text = filename.read_text()
            self.append('model-requests.jsonl', {'id': label, **cell, 'prompt_sha256': hashlib.sha256(text.encode()).hexdigest(), 'origin': 'LLM'})
            receipt = await infer(self.base / 'models' / label, text, semaphore)
            row = {'id': label, **cell, **receipt}
            if row['outcome'] == 'OK':
                row['metrics'] = evaluate(world(index, repeat), time_index, row['output'])
            self.rows.append(row);self.append('model-outputs.jsonl', row)
            print(json.dumps({'phase': phase, 'cell': label, 'outcome': row['outcome'], 'main_started': sum(r['phase'] == 'main' for r in self.rows)}), flush=True)
            return row
        return await asyncio.gather(*(one(mode) for mode in modes))

    def trial(self, phase: str, index: int, repeat: int) -> list:
        w = world(index, repeat)
        box = {}
        async def seed(client):
            box['binding'] = await self.seed(client, w)
        self.session(f'{phase}-{index}-{repeat}-seed', seed)
        output = []
        for time_index in (0, 1):
            if time_index:
                async def feedback(client):
                    await self.feedback(client, w, box['binding'])
                self.session(f'{phase}-{index}-{repeat}-feedback', feedback)
            rows = asyncio.run(self.cells(phase, index, repeat, time_index));output.extend(rows)
            async def audit(client):
                for row in rows:
                    if row['mode'] == 'S' and row['outcome'] == 'OK':
                        await self.audit(client, w, box['binding'], row)
            self.session(f'{phase}-{index}-{repeat}-{time_index}-audit', audit)
        return output


def freeze(base: Path) -> None:
    worlds = [world(i, r) for i in range(9) for r in (0, 1)]
    checks = [{'world': w['index'], 'repeat': w['repeat'], **exhaustive_check(w)} for w in worlds]
    write_json(base / 'worlds.json', worlds)
    write_json(base / 'oracle-contract.json', {'version': VERSION, 'loss': LOSS, 'checks': checks,
        'formula': '1 - (loss(selected)-loss(best))/(loss(worst)-loss(best))',
        'review': 'Safe deferral; separate bounded decision cost; not mathematical failure.'})
    equivalence = []
    prompts = base / 'frozen-prompts';prompts.mkdir()
    for w in worlds:
        for t in (0, 1):
            f = atoms(w, t)
            equivalence.append({'world': w['index'], 'repeat': w['repeat'], 'time': t,
                'equal': canonical_atoms(render(f, 'F'), 'F') == canonical_atoms(render(f, 'S'), 'S'),
                'atom_count': len(f), 'canonical_hash': digest(canonical_atoms(render(f, 'F'), 'F'))})
            for mode in ('F', 'S'):
                cell = {'phase': 'pilot' if w['index'] == 8 else 'main', 'world': w['index'], 'repeat': w['repeat'], 'time': t, 'mode': mode}
                (prompts / ('c' + digest(cell)[:20] + '.txt')).write_text(prompt(w, t, mode))
    write_json(base / 'treatment-equivalence.json', {'result': 'PASS' if all(r['equal'] for r in equivalence) else 'FAIL', 'checks': equivalence})
    write_json(base / 'schema.json', schema())
    write_json(base / 'preregistration.json', {'protocol': '003.1', 'frozen_utc': datetime.now(timezone.utc).isoformat(),
        'main_calls_maximum': 64, 'pilot_calls_maximum': 8, 'transport_calls': 2, 'model': MODEL,
        'reasoning': 'low', 'concurrency': CONCURRENCY, 'timeout': TIMEOUT, 'dry_timeout': 60,
        'input_tokens_estimated': 8000, 'immutable_model_build': None, 'model_seed': None,
        'backend_output_cap': None, 'rename_seeds': SEEDS, 'bootstrap_seed': 1003003,
        'bootstrap_draws': 10000, 'coverage_minimum': .9,
        'primary': 'Paired S-F transfer_decision_quality; world bootstrap, no imputation.',
        'H1': 'Lower CI>0, all8worlds, coverage>=.9, no safety/provenance deterioration, no ceiling.',
        'H2': 'Actual LLM grants are never activated; advisory correctness alone cannot establish a causal reduction in executed violations. INCONCLUSIVE unless identifiable; deterministic controls are mechanics.',
        'H3': 'Exploratory t1 negative-transfer differences, all8worlds and90% paired coverage; no transfer of causal claims from002.',
        'pilot_gate': 'All8 complete/schema-valid, F mean quality>=.30 and<.95, and F mean<=.85 or one secondary applicable/premise/discriminating metric<=.85. Otherwise stop; no automatic new pilot.',
        'stop': 'Any dry failure; invalid/ceiling pilot; attempted main world block pair coverage<.9; critical core defect; or64 main calls.',
        't1_intervention': 'Precommitted environmental measurement correction; same physical input, independent branch unchanged. No previous model outputs are added to prompts.',
        'logical_refs': 'QA fixture record addresses, bound after source/event creation to real project-local event IDs; not invented SQLite IDs.',
        'native_generation': False, 'production_changes_allowed': 'Only a reproduced MCP_CORE_BUG, never to pass the experiment.'})
    frozen = {str(p.relative_to(base)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in base.rglob('*') if p.is_file() and (p.parent == prompts or p.name in {'worlds.json', 'oracle-contract.json', 'schema.json', 'preregistration.json', 'treatment-equivalence.json'})}
    frozen.update({str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob('transfer_*.py')})
    root = Path(__file__).resolve().parents[1]
    for name in ('docs/LM_MICROTHEORY_TRANSFER_003_TZ.md', 'docs/LM_MICROTHEORY_TRANSFER_003_CODEX_PROMPT.md'):
        p = root / name
        frozen[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    write_json(base / 'immutable-manifest.json', frozen)
    for name in frozen:
        if not Path(name).is_absolute():
            (base / name).chmod(0o444)
    (base / 'immutable-manifest.json').chmod(0o444)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report-root', type=Path, default=Path(__file__).resolve().parents[1] / 'docs/qa/LM-MICROTHEORY-TRANSFER-003')
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    base = Path.home() / '.local/state/livingmath/microtheory-transfer' / stamp
    base.mkdir(parents=True, mode=0o700)
    report = args.report_root.resolve() / stamp
    config = configure();db = (Path(config['LIVE_MATH_DATA_DIR']).expanduser() / 'research.sqlite3').resolve(strict=True)
    with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as c:
        if c.execute('PRAGMA user_version').fetchone()[0] != 5:
            raise SystemExit('Refusing a migration or new database')
        with sqlite3.connect(base / 'research-before.sqlite3') as backup:
            c.backup(backup)
    (base / 'research-before.sqlite3').chmod(0o600)
    before = snapshot(db);write_json(base / 'before.json', before)
    metadata = {'private': str(base), 'report': str(report), 'endpoint': config['LIVE_MATH_PUBLIC_URL'] + '/mcp',
        'backup_sha256': hashlib.sha256((base / 'research-before.sqlite3').read_bytes()).hexdigest(),
        'code_before': {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob('*.py')},
        'AGENTS_sha256': hashlib.sha256((Path(__file__).resolve().parents[1] / 'AGENTS.md').read_bytes()).hexdigest(),
        'codex_version': subprocess.check_output(['codex', '--version'], text=True).strip(),
        'auth_mode': subprocess.check_output(['codex', 'login', 'status'], text=True, stderr=subprocess.STDOUT).strip(),
        'native_generation': False}
    write_json(base / 'metadata.json', metadata)
    (base / 'git-diff.txt').write_text(subprocess.check_output(['git', 'diff', '--no-ext-diff'], text=True))
    (base / 'git-status.txt').write_text(subprocess.check_output(['git', 'status', '--short'], text=True))
    print(json.dumps({'private': str(base), 'report': str(report)}), flush=True)
    exp = Experiment(base, report, config, db)
    try:
        exp.stage = 'local_validation'
        with (base / 'pytest.txt').open('w') as out:
            subprocess.run([sys.executable, '-m', 'pytest', str(Path(__file__).parent), '-q'], stdout=out, stderr=subprocess.STDOUT, check=True)
        freeze(base)
        exp.session('preflight', exp.preflight)
        exp.stage = 'real_86_regression'
        with (base / 'regression-log.txt').open('w') as out:
            subprocess.run([sys.executable, str(Path(__file__).with_name('qa_positive_acceptance.py')),
                '--out', str(base / ('regression-' + stamp))], stdout=out, stderr=subprocess.STDOUT, check=True)
        exp.session('controls', exp.deterministic_controls)
        exp.stage = 'transport_dry_run'
        async def dry():
            sem = asyncio.Semaphore(CONCURRENCY)
            return await asyncio.gather(*(infer(base / 'models' / ('dry-' + str(i)),
                'No tools or files. Return exactly {"ok":true}.', sem, timeout=60, short=True) for i in range(2)))
        dry_rows = asyncio.run(dry());write_json(base / 'transport-dry-run.json', dry_rows)
        if any(r['outcome'] != 'OK' or r['output'] != {'ok': True} for r in dry_rows):
            raise StopExperiment('TRANSPORT_FAILURE', 'Transport/provider dry-run failed; scientific matrix not started')
        exp.stage = 'difficulty_pilot'
        pilot = exp.trial('pilot', 8, 0) + exp.trial('pilot', 8, 1)
        flat = [r['metrics'] for r in pilot if r['mode'] == 'F' and r['outcome'] == 'OK']
        if len(flat) != 4 or any(r['outcome'] != 'OK' for r in pilot):
            raise StopExperiment('TRANSPORT_FAILURE' if any(r['outcome'] == 'TRANSPORT_FAILURE' for r in pilot) else 'PROMPT_SCHEMA_BUG', 'Pilot coverage/schema gate failed')
        import statistics
        mean = statistics.mean(m['quality'] for m in flat)
        secondary = min(statistics.mean(m[key] for m in flat) for key in ('applicable_theory', 'critical_premise', 'discriminating_test'))
        write_json(base / 'pilot-gate.json', {'F_mean_quality': mean, 'F_min_secondary': secondary, 'excluded_from_main': True})
        if not (.3 <= mean < .95 and (mean <= .85 or secondary <= .85)):
            raise StopExperiment('QA_WORLD_BUG', 'Pilot difficulty gate: ceiling or unsuitable difficulty; no main matrix or automatic expansion')
        exp.stage = 'main'
        for i in range(8):
            block = exp.trial('main', i, 0) + exp.trial('main', i, 1)
            pairs = [(next(r for r in block if r['repeat'] == rep and r['time'] == t and r['mode'] == 'F'),
                      next(r for r in block if r['repeat'] == rep and r['time'] == t and r['mode'] == 'S')) for rep in (0, 1) for t in (0, 1)]
            coverage = sum(a['outcome'] == b['outcome'] == 'OK' for a, b in pairs) / 4
            if coverage < .9:
                raise StopExperiment('TRANSPORT_FAILURE' if any(r['outcome'] == 'TRANSPORT_FAILURE' for r in block) else 'PROMPT_SCHEMA_BUG', 'Attempted world block pair coverage below90%; stopping without retries')
        exp.stage = 'completed'
    except StopExperiment as error:
        exp.failures.append({'classification': error.classification, 'stage': exp.stage, 'reason': str(error)})
    except BaseException as error:
        import traceback
        (base / 'exception.txt').write_text(traceback.format_exc())
        exp.failures.append({'classification': 'TRANSPORT_FAILURE' if isinstance(error, (httpx.HTTPError, ConnectionError)) else 'PROTOCOL_DEVIATION', 'stage': exp.stage, 'reason': type(error).__name__ + ': ' + str(error)})
    finally:
        # Account for interrupted starts without another inference or inferred timing.
        known = {r['id'] for r in exp.rows}
        request_path = base / 'model-requests.jsonl'
        pending = [json.loads(line) for line in request_path.read_text().splitlines()] if request_path.exists() else []
        for request in pending:
            label = request['id'];directory = base / 'models' / label
            if label not in known and (directory / 'attempt-start.json').exists():
                receipt = json.loads((directory / 'receipt.json').read_text()) if (directory / 'receipt.json').exists() else {
                    'outcome': 'TRANSPORT_FAILURE', 'metadata': {'actual_usage': None, 'wall_seconds': None,
                    'measurement_limitation': 'Started request interrupted before a receipt; no inferred timing or retry.'}}
                if receipt['outcome'] == 'OK':
                    receipt = {'outcome': 'MODEL_FAILURE', 'metadata': receipt['metadata'],
                        'error': 'Provider output exists but controller/oracle failed before scoring; original output retained.'}
                row = {**request, **receipt, 'interrupted_attempt_reconciled': True}
                exp.append('model-outputs.jsonl', row);exp.rows.append(row)
        try:
            async def cleanup(client):
                store = ResearchStore(db)
                own = 'LM_QA_MT003_' + stamp + '_'
                regression = base / ('regression-' + stamp) / 'result.json'
                extra_project = json.loads(regression.read_text()).get('project') if regression.exists() else None
                with store._connect() as connection:
                    moves = [(row['project'], row['id']) for row in connection.execute('SELECT project,id FROM research_moves')
                             if row['project'].startswith(own) or row['project'] == extra_project]
                for project, mid in moves:
                    state = store.moves.inspect(project, mid)
                    if state['status'] not in {'COMPLETED', 'ABANDONED', 'REJECTED'}:
                        await client.call('transition_research_move', {'project': project, 'move_id': mid,
                            'action': 'abandon', 'reason': 'End of this preregistered QA run; retain all earlier failures.',
                            'request_key': project + ':cleanup:' + str(mid)})
            exp.session('cleanup', cleanup)
        except Exception as error:
            exp.failures.append({'classification': 'TRANSPORT_FAILURE', 'stage': 'cleanup', 'reason': type(error).__name__})
        try:
            async def postflight(client):
                write_json(base / 'postflight.json', {'health': await client.call('service_health', {}),
                    'rh_frontier': await client.call('research_frontier', {'project': 'RH', 'include_closed': True})})
            exp.session('postflight', postflight)
        except Exception as error:
            exp.failures.append({'classification': 'TRANSPORT_FAILURE', 'stage': 'postflight', 'reason': type(error).__name__})
        write_json(base / 'failures.json', exp.failures)
        write_json(base / 'stage.json', {'stage': exp.stage})
        children = resource.getrusage(resource.RUSAGE_CHILDREN);server_end = server_cpu()
        write_json(base / 'cost.json', {'client_cpu_seconds': time.process_time() - exp.cpu_start,
            'children_cpu_seconds': children.ru_utime + children.ru_stime - exp.children_start.ru_utime - exp.children_start.ru_stime,
            'server_cpu_seconds': server_end['seconds'] - exp.server_start['seconds'] if server_end['pid'] == exp.server_start['pid'] else None,
            'wall_seconds': time.monotonic() - exp.start, 'remote_cpu_seconds': None})
        from transfer_report import export
        export(base)
        print(json.dumps({'finished': True, 'stage': exp.stage, 'report': str(report / 'report.md'), 'failures': exp.failures}), flush=True)


if __name__ == '__main__':
    main()
