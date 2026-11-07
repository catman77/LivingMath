"""Project-owned frozen receipts and append-only counterfactual records."""
import base64
import copy
from pathlib import Path
from ..core import canonical, digest
from ..white_star import blobs
from ..symbolic.state import require
from .service import NLService
from .decoder import replay_bundle
from .provenance import traces
from .causal import redecode


def deterministic(value):
    """Runtime measurements are evidence, not replay equality inputs."""
    if isinstance(value, dict):
        return {k: deterministic(v) for k, v in value.items() if k not in ('CPU_ms', 'CPU_ceiling_ms')}
    if isinstance(value, list):
        return [deterministic(v) for v in value]
    return value


class CausalService:
    def __init__(self, root, executor=None):
        self.root = Path(root)
        self.nl = NLService(root, executor)

    def load(self, w, ref):
        row = next((r for r in w.history() if r['action'] == 'nl.causal.finish' and r['result']['run_ref'] == ref), None)
        require(row is not None, 'NOT_FOUND')
        return w.get(row['result']['record_ref'])

    def owns(self, project, ref):
        w = self.nl.formal.ext.workspace(project)
        with w.locked():
            return any(r['action'] == 'nl.causal.finish' and r['result']['run_ref'] == ref for r in w.history())

    def execute(self, project, key, args):
        w = self.nl.formal.ext.workspace(project)
        namespaced = 'nl.causal:' + digest(key)
        # Repeats return the exact persisted result, even after a newer receipt
        # or policy becomes available. Different payloads cannot reuse a key.
        with w.locked():
            row = next((r for r in w.history() if r['request_key'] == namespaced), None)
            if row:
                require(row['payload_digest'] == digest({'action': 'nl.causal.finish', 'payload': args}), 'REQUEST_KEY_CONFLICT')
                return w.get(row['result']['record_ref'])
            source = self.nl.load(w, args['source_nl_run_ref'])
            require(source['status'] == 'COMPLETED', 'SOURCE_NOT_COMPLETED')
            original = blobs.get(w, source['result_ref'])
            require(digest(original) == source['result_sha256'], 'REJECTED_PROVENANCE')
            bundle = original.get('bundle')
            require(bundle is not None and bundle.get('receipt', {}).get('status') == 'OK', 'FROZEN_RECEIPT_UNAVAILABLE')
            replay_bundle(bundle)
            indices = args['source_item_indices']
            require(len(set(indices)) == len(indices) and all(i < len(bundle['items']) for i in indices), 'SOURCE_ITEM_BOUND')
            require(len(set(args['arms'])) == len(args['arms']), 'DUPLICATE_ARM')
            sources = {}
            for i in indices:
                item = bundle['items'][i]
                owned = self.nl.formal.owned(w, item['source_ref'])
                require(owned == item['packet']['source'], 'SOURCE_BINDING_MISMATCH')
                sources[i] = owned
        # provenance.traces loads/locks the same Workspace. Resolve outside the
        # transaction to avoid recursive flock deadlock. Objects are immutable.
        checked = {str(i): [] for i in indices}
        for ref in args.get('structural_run_refs', []):
            from ..symbolic.service import SymbolicService
            from ..white_star.service import WhiteStar
            svc = SymbolicService(self.root, None) if ref['engine'] == 'symbolic_v1' else WhiteStar(self.root, None)
            _, run = svc.load(project, ref['run_id'])
            matched = [i for i in indices if sources[i]['sha256'] == run['source_sha256']]
            require(bool(matched), 'SOURCE_BINDING_MISMATCH')
            for i in matched:
                checked[str(i)].extend(traces(self.root, project, sources[i], [ref], 4))
                require(len(checked[str(i)]) <= 4, 'FRAME_BOUND')
        if any(a in args['arms'] for a in ('REAL_TRACE', 'SHAM_ORDER')):
            require(all(checked[str(i)] for i in indices), 'UNBACKED_ORIGIN')
        value = redecode(bundle, indices, checked, args['arms'], args['policy'])
        frozen = {'schema': 'nl-causal-bundle/1', 'source_nl_run_ref': source['run_ref'],
                  'source_result_sha256': source['result_sha256'], 'source_bundle': bundle,
                  'source_item_indices': indices, 'structural': checked, 'arms': args['arms'],
                  'policy': args['policy'], 'expected_sha256': digest(deterministic(value))}
        run_ref = digest([project, namespaced, args])
        def commit(rows):
            rr, refs = blobs.put(w, value)
            br, more = blobs.put(w, frozen)
            record = {'schema': 'nl-causal-run/1', 'run_ref': run_ref, 'status': 'COMPLETED',
                      'source_nl_run_ref': source['run_ref'], 'result_ref': rr, 'result_sha256': digest(value),
                      'bundle_ref': br, 'deterministic_sha256': frozen['expected_sha256'],
                      'model_calls_delta': 0, 'network_calls': 0, 'execution_permission': False}
            ref = w.put(record)
            return {'run_ref': run_ref, 'record_ref': ref}, [ref, *refs, *more]
        row = w.transact('nl.causal.finish', namespaced, args, commit)
        return w.get(row['record_ref'])

    def inspect(self, project, run_ref, view='summary', expected_ast_sha256=None, offset=0, limit=32):
        w = self.nl.formal.ext.workspace(project)
        with w.locked():
            record = self.load(w, run_ref)
            if view == 'summary':
                return record
            value = blobs.get(w, record['result_ref'])
            require(digest(value) == record['result_sha256'], 'REJECTED_PROVENANCE')
            if expected_ast_sha256:
                require(any(c['candidate_ast_sha256'] == expected_ast_sha256 for i in value['items'] for a in i['arms'].values() for c in a['candidates']), 'REJECTED_PROVENANCE')
            if view in ('replay', 'bundle'):
                bundle = blobs.get(w, record['bundle_ref'])
                require(bundle['expected_sha256'] == record['deterministic_sha256'], 'REJECTED_PROVENANCE')
                if view == 'replay':
                    replayed = redecode(bundle['source_bundle'], bundle['source_item_indices'], bundle['structural'], bundle['arms'], bundle['policy'])
                    actual = digest(deterministic(replayed))
                    return {'status': 'REPLAY_MATCH' if actual == bundle['expected_sha256'] else 'REPLAY_BOUND_DIVERGENCE',
                            'expected_sha256': bundle['expected_sha256'], 'actual_sha256': actual,
                            'LLM_calls': 0, 'network_calls': 0, 'execution_permission': False}
                value = bundle
            raw = canonical(value).encode()
            if len(raw) > 50000 or offset:
                chunk = raw[offset:offset + min(limit * 1024, 49152)]
                return {'encoding': 'base64', 'data': base64.b64encode(chunk).decode(), 'bytes': len(raw),
                        'sha256': digest(value), 'offset': offset, 'next_offset': offset + len(chunk) if offset + len(chunk) < len(raw) else None}
            return value
