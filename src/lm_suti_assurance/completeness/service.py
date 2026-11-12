"""Append-only project-owned coverage; receipts/checkpoint commit together."""
from pathlib import Path
from ..core import canonical, digest
from ..errors import AssuranceError
from ..service import Service
from ..symbolic.state import require
from ..white_star import blobs
from .contracts import TOOLS, check_schema, validate, kernel_binding
from .verify import verify_plan, verify_row

ZERO = '0'*64


def receipt_check(plan: dict, record: dict, index: int) -> None:
    row = plan['obligations'][index]
    require(canonical({k: record.get(k) for k in row}) == canonical(row), 'RECEIPT_MISMATCH')
    verify_row(plan, row)
    require(record.get('plan_sha256') == plan['plan_sha256'] and record.get('kernel_binding') == plan['kernel_binding'], 'RECEIPT_MISMATCH')
    require(record.get('work_unit_key') == digest([plan['plan_sha256'], row['task_id']]), 'RECEIPT_MISMATCH')
    require(record.get('integer_projection_checked') is True and record.get('zero_fibre_checked') is True and record.get('primitive') == 'SUPPLIED_cad.project', 'RECEIPT_MISMATCH')
    require(record.get('execution_permission') is False and record.get('source_truth') == 'NOT_VERIFIED', 'FALSE_VERIFICATION_CLAIM')
    require(record.get('receipt_sha256') == digest({k: v for k, v in record.items() if k != 'receipt_sha256'}), 'RECEIPT_HASH_MISMATCH')


class CoverageService:
    def __init__(self, root, executor=None):
        self.base = Service(Path(root))
        self.executor = executor

    def _worker(self, packet):
        require(self.executor is not None, 'ENGINE_UNAVAILABLE')
        return self.executor.run(packet)['data']

    def plan(self, project: str, request_key: str, source_request: dict, scope: dict) -> dict:
        check_schema(dict(project=project, request_key=request_key, source_request=source_request, scope=scope), TOOLS['coverage_plan'])
        validate(source_request, scope)
        binding = kernel_binding()
        w = self.base.workspace(project)
        def save(rows):
            value = self._worker({'operation': 'plan', 'source_request': source_request})
            plan = value['plan']
            check = verify_plan(source_request, plan, binding['sha256'])
            source_ref = w.put(source_request['encoding']['source'])
            encoding_ref = w.put(source_request['encoding'])
            require(source_ref == plan['source_ref'] and encoding_ref == plan['encoding_ref'], 'SOURCE_BINDING_MISMATCH')
            atlas_blob_ref, ar = blobs.put(w, plan['atlas'])
            request_ref, rr = blobs.put(w, source_request)
            plan_ref, pr = blobs.put(w, plan)
            return {'plan_ref': plan_ref, 'request_ref': request_ref, 'plan_sha256': plan['plan_sha256'],
                    'total_count': plan['total_count'], 'kernel_binding': plan['kernel_binding'],
                    'atlas_blob_ref': atlas_blob_ref, 'independent_check': check, 'execution_permission': False}, [source_ref, encoding_ref, *ar, *rr, *pr]
        value = w.transact('coverage.plan', 'coverage-plan:'+digest(request_key), {'source_request': source_request, 'scope': scope, 'kernel_binding': binding['sha256']}, save)
        return {**value, 'status': 'PLANNED', 'compute_complete': False, 'export_available': False, 'delivery_acked': False,
                'cursor': {'plan_ref': value['plan_ref'], 'index': 0, 'prefix_sha256': ZERO}}

    def _load(self, w, plan_ref, rows):
        owned = next((r['result'] for r in rows if r['action'] == 'coverage.plan' and r['result']['plan_ref'] == plan_ref), None)
        require(owned is not None, 'PLAN_NOT_FOUND')
        plan = blobs.get(w, plan_ref)
        request = blobs.get(w, owned['request_ref'])
        require(digest(w.get(plan['source_ref'])) == plan['source_ref'] and digest(w.get(plan['encoding_ref'])) == plan['encoding_ref'], 'SOURCE_BINDING_MISMATCH')
        require(digest(blobs.get(w, owned['atlas_blob_ref'])) == plan['atlas_ref'], 'ATLAS_BINDING_MISMATCH')
        require(plan['kernel_binding'] == kernel_binding()['sha256'], 'KERNEL_BINDING_MISMATCH')
        verify_plan(request, plan, plan['kernel_binding'])
        return plan, request

    def _prefix(self, w, plan_ref, plan, rows):
        records, prefix = [], ZERO
        for row in rows:
            if row['action'] != 'coverage.advance' or row['result']['plan_ref'] != plan_ref:
                continue
            result = row['result']
            require(result['start_index'] == len(records) and result['previous_prefix_sha256'] == prefix, 'JOURNAL_PREFIX_MISMATCH')
            for r in blobs.get(w, result['receipts_ref']):
                require(len(records) < plan['total_count'], 'JOURNAL_PREFIX_MISMATCH')
                receipt_check(plan, r, len(records))
                records.append(r)
                prefix = digest([prefix, r['receipt_sha256']])
            require(result['cursor'] == {'plan_ref': plan_ref, 'index': len(records), 'prefix_sha256': prefix}, 'JOURNAL_PREFIX_MISMATCH')
        return records, prefix

    def _summary(self, plan_ref, plan, records, prefix, rows):
        complete = len(records) == plan['total_count']
        export_digest = digest(records) if complete else None
        acked = complete and any(r['action'] == 'coverage.ack' and r['result']['plan_ref'] == plan_ref and r['result']['export_sha256'] == export_digest for r in rows)
        return {'schema': 'certified-coverage-status/1', 'plan_ref': plan_ref, 'plan_sha256': plan['plan_sha256'],
                'status': 'COMPLETE' if complete else 'PARTIAL', 'computed_count': len(records), 'total_count': plan['total_count'],
                'compute_complete': complete, 'export_available': complete, 'delivery_acked': acked,
                'export_sha256': export_digest, 'cursor': {'plan_ref': plan_ref, 'index': len(records), 'prefix_sha256': prefix},
                'source_ref': plan['source_ref'], 'source_sha256': plan['source_sha256'], 'encoding_ref': plan['encoding_ref'],
                'atlas_ref': plan['atlas_ref'], 'observer_version': plan['observer_version'], 'seed': plan['seed'],
                'scope': plan['scope'], 'kernel_binding': plan['kernel_binding'],
                'coefficient_bound_H': plan['coefficient_bound_H'], 'witness_l1_bound': plan['witness_l1_bound'],
                'coordinate_abs_bound': plan['coordinate_abs_bound'], 'numeric_charts': len(plan['atlas']['charts']),
                'omitted_collinear_pair_count': len(plan['atlas']['omitted_collinear_pairs']),
                'witness_origin': 'CONSTRUCTED_CERTIFIED_WITNESS', 'source_truth': 'NOT_VERIFIED', 'execution_permission': False}

    def advance(self, project: str, plan_ref: str, request_key: str, cursor: dict, work_budget: int) -> dict:
        check_schema(dict(project=project, plan_ref=plan_ref, request_key=request_key, cursor=cursor, work_budget=work_budget), TOOLS['coverage_advance'])
        w = self.base.workspace(project)
        def save(rows):
            plan, request = self._load(w, plan_ref, rows)
            records, prefix = self._prefix(w, plan_ref, plan, rows)
            start = len(records)
            require(cursor == {'plan_ref': plan_ref, 'index': start, 'prefix_sha256': prefix}, 'CURSOR_PREFIX_MISMATCH')
            error = None
            try:
                batch = self._worker({'operation': 'execute', 'source_request': request, 'plan': plan, 'index': start, 'budget': work_budget})['records'] if work_budget and start < plan['total_count'] else []
                require(len(batch) == min(work_budget, plan['total_count']-start), 'INCOMPLETE_WORKER_BATCH')
                for i, r in enumerate(batch, start):
                    receipt_check(plan, r, i)
            except Exception as e:
                batch = []
                error = {'code': e.code if isinstance(e, AssuranceError) else 'COVERAGE_WORKER_ERROR', 'message': str(e)[:256], 'unclosed_obligation': start}
            new_prefix = prefix
            for r in batch:
                new_prefix = digest([new_prefix, r['receipt_sha256']])
            ref, refs = blobs.put(w, batch)
            result = {**self._summary(plan_ref, plan, records+batch, new_prefix, rows), 'start_index': start,
                      'previous_prefix_sha256': prefix, 'receipts_ref': ref, 'advanced_count': len(batch), 'error': error}
            if error:
                result['status'] = 'ERROR'
            return result, refs
        return w.transact('coverage.advance', 'coverage-advance:'+digest(request_key), {'plan_ref': plan_ref, 'cursor': cursor, 'work_budget': work_budget}, save)

    def inspect(self, project: str, plan_ref: str, view: str = 'summary', cursor: int = 0, page_size: int = 64, acknowledgement: dict | None = None, request_key: str | None = None) -> dict:
        args = dict(project=project, plan_ref=plan_ref, view=view, cursor=cursor, page_size=page_size)
        if acknowledgement is not None:
            args['acknowledgement'] = acknowledgement
        if request_key is not None:
            args['request_key'] = request_key
        check_schema(args, TOOLS['coverage_inspect'])
        w = self.base.workspace(project)
        if acknowledgement is not None:
            require(view == 'delivery' and request_key is not None, 'EXPLICIT_DELIVERY_ACK_REQUIRED')
            def ack(rows):
                plan, _ = self._load(w, plan_ref, rows)
                records, prefix = self._prefix(w, plan_ref, plan, rows)
                summary = self._summary(plan_ref, plan, records, prefix, rows)
                require(summary['compute_complete'] and acknowledgement['record_count'] == len(records) and acknowledgement['export_sha256'] == summary['export_sha256'], 'DELIVERY_ACK_MISMATCH')
                return {'plan_ref': plan_ref, **acknowledgement, 'ack_kind': 'CLIENT_DECLARED_RECEIPT_NOT_SEMANTIC_COMPREHENSION', 'execution_permission': False}, []
            w.transact('coverage.ack', 'coverage-ack:'+digest(request_key), {'plan_ref': plan_ref, **acknowledgement}, ack)
        with w.locked():
            rows = w.history()
            plan, _ = self._load(w, plan_ref, rows)
            records, prefix = self._prefix(w, plan_ref, plan, rows)
            summary = self._summary(plan_ref, plan, records, prefix, rows)
            if view in ('summary', 'delivery'):
                return summary
            items = {'plan': plan['obligations'], 'atlas': plan['atlas']['charts'], 'omissions': plan['atlas']['omitted_collinear_pairs'], 'records': records}[view]
            require(cursor <= len(items), 'INVALID_PAGE_CURSOR')
            page = items[cursor:cursor+page_size]
            while len(canonical(page).encode()) > 200000 and page:
                page.pop()
            require(bool(page) or cursor == len(items), 'RECORD_TOO_LARGE_FOR_PAGE')
            stop = cursor+len(page)
            return {**summary, 'view': view, 'records': page, 'offset': cursor, 'page_count': len(page),
                    'available_count': len(items), 'next_cursor': stop if stop < len(items) else None,
                    'page_sha256': digest(page), 'scope': plan['scope'], 'kernel_binding': plan['kernel_binding'],
                    'atlas_ref': plan['atlas_ref'],
                    'decoder_surface': 'FULL_TARGET_RECORDS_NO_FRAME_TRUNCATION'}

    def replay(self, project: str, plan_ref: str, cursor: int = 0, work_budget: int = 64) -> dict:
        check_schema(dict(project=project, plan_ref=plan_ref, cursor=cursor, work_budget=work_budget), TOOLS['coverage_replay'])
        w = self.base.workspace(project)
        with w.locked():
            rows = w.history()
            plan, request = self._load(w, plan_ref, rows)
            records, _ = self._prefix(w, plan_ref, plan, rows)
            require(cursor <= len(records), 'INVALID_REPLAY_CURSOR')
            size = min(work_budget, len(records)-cursor)
            new = self._worker({'operation': 'execute', 'source_request': request, 'plan': plan, 'index': cursor, 'budget': size})
            require(new['records'] == records[cursor:cursor+size], 'COVERAGE_REPLAY_MISMATCH')
            return {'status': 'REPLAY_MATCH', 'plan_ref': plan_ref, 'checked_count': size, 'next_cursor': cursor+size if cursor+size < len(records) else None,
                    'total_count': plan['total_count'], 'computed_count': len(records), 'kernel_binding': plan['kernel_binding'],
                    'independent_check': new['independent_check'], 'source_truth': 'NOT_VERIFIED', 'execution_permission': False}
