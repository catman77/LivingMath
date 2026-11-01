"""Small explicit entrypoints. No scheduler, hidden harvesting, or implicit model calls."""
import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import tempfile

import httpx

from roblox_pred.config import authorize, digest, load_config, registry
from roblox_pred.evaluation.runner import evaluate, synthetic_samples
from roblox_pred.features.dataset import build_dataset
from roblox_pred.semantic import native_contract, unavailable
from roblox_pred.sources import RobloxPublicSource
from roblox_pred.storage import Store


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))


def output_path(root, config, args):
    return Path(args.output).resolve() if args.output else root/config['report_directory']/'private'/'baseline'


def main(command: str) -> int:
    parser = argparse.ArgumentParser(description='ROBLOX-PRED-001: аудит и изолированный исследовательский прогон')
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', help='Отдельный каталог результата; не каталог production')
    if command == 'run_baseline': parser.add_argument('--smoke', action='store_true')
    if command == 'run_semantic': parser.add_argument('--dry-run', action='store_true')
    if command == 'audit_sources': parser.add_argument('--live', action='store_true')
    args = parser.parse_args()
    try:
        config, root = load_config(args.config)
        if command == 'audit_sources':
            if args.live:
                policy = registry(root, config)[config['collection']['source_id']]
                _, _, receipt = RobloxPublicSource(policy, root, config['audit']).fetch(config['audit']['requested_universe_ids'])
                emit({'scope': 'LIVE_AUTHORIZED_TRANSPORT_ONLY', 'receipt': receipt})
            else:
                recorded = json.loads((root/'reports'/'data-audit.json').read_text())
                emit({'mode': 'RECORDED_AUDIT_REPLAY_NO_NETWORK', 'audit': recorded,
                    'current_source_policies': [p.model_dump() for p in registry(root, config).values()]})
            return 0
        if command == 'collect_snapshots':
            collect = config['collection']; policy = registry(root, config)[collect['source_id']]
            authorize(policy, root, collect=True)  # Checked before opening database or network.
            if not collect['enabled']:
                raise ValueError('COLLECTION_DISABLED_NO_SCHEDULER_INSTALLED')
            if collect['max_cycles'] != 1:
                raise ValueError('BOUNDED_SINGLE_CYCLE_REQUIRED_USE_EXTERNAL_APPROVED_SCHEDULE')
            frame_path = root/'data'/'input'/'prospective-frame.json'
            frame = json.loads(frame_path.read_text())
            if (set(frame['universe_ids']) != set(collect['universe_ids'])
                    or frame['frame_id'] != config['cohort']['frame_id']
                    or datetime.fromisoformat(frame['frozen_at']) >= datetime.now(UTC)):
                raise ValueError('PROSPECTIVE_FIXED_FRAME_REQUIRED')
            # Freeze *before* the first call; future additions need a separate cohort/version.
            from roblox_pred.evaluation.runner import freeze
            freeze(root/'data'/'processed'/'prospective-frame-frozen.json', {
                'frame': frame, 'protocol': config, 'source_policy': policy.model_dump()})
            journal = root/'data'/'raw'/'collection-journal.jsonl'
            journal.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            attempt = {'attempt_id': digest([frame['frame_id'], datetime.now(UTC).isoformat()]),
                'requested_at': datetime.now(UTC).isoformat(), 'universe_ids': collect['universe_ids']}
            try:
                games, snapshots, receipt = RobloxPublicSource(policy, root, config['audit']).fetch(collect['universe_ids'])
                store = Store(root/config['storage']['directory'], root/config['storage']['database'])
                store.append('games', games); store.append('snapshots', snapshots)
                attempt.update(status='CAPTURED', receipt=receipt,
                    unknown=sum(s.status != 'OBSERVED' for s in snapshots))
            except (ValueError, OSError, httpx.HTTPError) as error:
                attempt.update(status='CENSORED_REQUEST_FAILURE', error=str(error), count_values=None)
                raise
            finally:
                with journal.open('a') as stream: stream.write(json.dumps(attempt)+'\n')
                journal.chmod(0o600)
            emit(attempt); return 0
        if command == 'run_semantic':
            if not args.dry_run:
                raise ValueError('NATIVE_ROBLOX_BINDING_NOT_IDENTIFIED; Stage B закрыт data gate')
            samples, _ = synthetic_samples(config['seed'])
            contract = native_contract(samples[0], [])
            emit({'scope': 'SYNTHETIC_CONTRACT_DRY_RUN', 'native_execution': False, 'llm_calls': 0,
                  'request': contract, 'result': unavailable(samples[0]).model_dump(mode='json')})
            return 0
        if command == 'run_baseline' and args.smoke:
            samples, manifest = synthetic_samples(config['seed'])
            # No default mixing with real artifacts: fresh private engineering directory.
            output = Path(args.output).resolve() if args.output else Path(tempfile.mkdtemp(prefix='roblox-pred-smoke-'))
            result = evaluate(samples, manifest, config, output, smoke=True)
            emit({'output_directory': str(output), **result}); return 0
        samples, manifest, tables = build_dataset(root, config)
        if command == 'build_dataset':
            store = Store(root/config['storage']['directory'], root/config['storage']['database'])
            for table, records in tables.items(): store.append(table, records)
            emit({'status': 'DATASET_BUILT_NOT_EVALUATED', **manifest, 'parts': store.manifest()})
        elif command in {'run_baseline', 'run_eval'}:
            if command == 'run_eval' and not (output_path(root, config, args)/'evaluation.json').exists():
                raise ValueError('BASELINE_MUST_BE_FROZEN_AND_RUN_FIRST')
            emit(evaluate(samples, manifest, config, output_path(root, config, args)))
        else:
            raise ValueError('UNKNOWN_COMMAND')
        return 0
    except (ValueError, KeyError, OSError, httpx.HTTPError) as error:
        emit({'status': 'BLOCKED', 'research_conclusion': 'INCONCLUSIVE', 'error': str(error),
            'message_ru': 'Команда остановлена. Проверки не ослаблены; реальные метрики не получены.'})
        return 3
