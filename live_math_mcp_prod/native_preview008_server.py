"""Standalone trusted-stdio preview; integration into owner OAuth is an unapplied patch."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from native_preview008_contract import (VERSION, NativeQuestion, NativeRequest, NormalizeRequest, Observer,
                                       PreviewBudget, Project, QueryScope, SourceBinding, EventID, refusal)


class MeasuredProcess(subprocess.Popen):
    """Per-child OS usage through exit, including encoding and interpreter teardown.

    wait4 replaces both Popen reap paths; concurrent workers cannot contaminate
    one another as they would with process-global RUSAGE_CHILDREN differences.
    """
    def __init__(self, *args, **kwargs):
        self.child_usage = None
        super().__init__(*args, **kwargs)

    def _try_wait(self, wait_flags):
        try:
            pid, status, usage = os.wait4(self.pid, wait_flags)
        except ChildProcessError:
            return self.pid, 0
        if pid == self.pid:
            self.child_usage = usage
        return pid, status

    def _internal_poll(self, _deadstate=None):
        if self.returncode is not None or not self._waitpid_lock.acquire(False):
            return self.returncode
        try:
            pid, status = self._try_wait(os.WNOHANG)
            if pid == self.pid:
                self._handle_exitstatus(status)
        finally:
            self._waitpid_lock.release()
        return self.returncode


class PreviewBoundary:
    def __init__(self, database: Path):
        self.database = database.expanduser().resolve(strict=True)
        self.worker = Path(__file__).with_name('native_preview008_worker.py')

    def run(self, kind: str, arguments: dict) -> dict:
        start, cpu = time.perf_counter_ns(), time.thread_time_ns()
        request = (NativeRequest if kind == 'native' else NormalizeRequest).model_validate(arguments)
        raw = json.dumps(request.model_dump(), ensure_ascii=False, allow_nan=False).encode()
        if len(raw) > request.budget.input_bytes:
            return refusal('INSUFFICIENT_CONTEXT', 'INPUT_BYTE_BOUND')
        process = MeasuredProcess([sys.executable, str(self.worker), str(self.database), kind,
                                    str(request.budget.memory_mb), str(request.budget.deadline_ms)],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True, cwd=str(self.worker.parent),
                                   env={'PATH': os.defpath, 'LANG': 'C.UTF-8', 'PYTHONHASHSEED': '0',
                                        'PYTHONDONTWRITEBYTECODE': '1'})
        try:
            data, error = process.communicate(raw, timeout=request.budget.deadline_ms / 1000)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            out = refusal('RESOURCE_LIMIT', 'HARD_WORKER_TIMEOUT')
        else:
            if process.returncode != 0 or len(data) > request.budget.output_bytes:
                out = refusal('RESOURCE_LIMIT' if process.returncode < 0 else 'WORKER_FAILURE',
                              'WORKER_EXIT_OR_OUTPUT_BOUND')
                out['worker_exit_code'] = process.returncode
                out['worker_stderr_sha256'] = hashlib.sha256(error).hexdigest()
            else:
                try:
                    out = json.loads(data)
                    if not isinstance(out, dict):
                        raise ValueError('Invalid worker envelope')
                except (ValueError, TypeError):
                    out = refusal('WORKER_FAILURE', 'INVALID_WORKER_RESPONSE')
        out['proof_status'] = 'unverified'
        out['execution_permission'] = {'allowed': False}
        out['cold_wall_ns'] = time.perf_counter_ns() - start
        out['parent_cpu_ns'] = time.thread_time_ns() - cpu
        usage = process.child_usage
        out['child_usage_status'] = 'OS_WAIT4_THROUGH_EXIT' if usage is not None else 'UNAVAILABLE'
        out['child_cpu_ns'] = round((usage.ru_utime + usage.ru_stime) * 1_000_000_000) if usage is not None else None
        out['child_peak_rss_KiB'] = usage.ru_maxrss if usage is not None else None
        out['CPU_scope'] = 'OS wait4 child user+system CPU through exit; boundary parent thread CPU separately. MCP event-loop/transport CPU outside the boundary is not included.'
        out['cost_scope'] = 'Cold process launch/imports + SELECT snapshot + normalization + I/native replay + independent T + serialization; no cache amortization.'
        return out


def register_preview_tools(mcp: FastMCP, database: Path) -> None:
    boundary = PreviewBoundary(database)
    semaphore = asyncio.Semaphore(2)
    annotations = ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                                  idempotentHint=True, openWorldHint=False)

    @mcp.tool(annotations=annotations)
    async def research_normalize_preview(project: Project, focus: str, source_event_ids: list[EventID],
                                         query_scope: QueryScope, budget: PreviewBudget = PreviewBudget()) -> dict:
        """Read-only source-preserving004.1. C4 is explanation only; no grants or audit-log writes."""
        arguments = {'project': project, 'focus': focus, 'source_event_ids': source_event_ids,
                     'query_scope': query_scope.model_dump(), 'budget': budget.model_dump()}
        async with semaphore:
            return await asyncio.to_thread(boundary.run, 'normalize', arguments)

    @mcp.tool(annotations=annotations)
    async def research_native_preview(project: Project, active_frontier_id: EventID, active_frontier_version: EventID,
                                      source_event_ids: list[EventID], source_adapter_id: str,
                                      source_bindings: list[SourceBinding], observer: Observer,
                                      question: NativeQuestion, budget: PreviewBudget = PreviewBudget()) -> dict:
        """Bounded source replay with I006.2/optional007.2 and unchanged T; never executes an external experiment."""
        arguments = {'project': project, 'active_frontier_id': active_frontier_id,
                     'active_frontier_version': active_frontier_version, 'source_event_ids': source_event_ids,
                     'source_adapter_id': source_adapter_id, 'source_bindings': [s.model_dump() for s in source_bindings],
                     'observer': observer.model_dump(), 'question': question.model_dump(), 'budget': budget.model_dump()}
        async with semaphore:
            return await asyncio.to_thread(boundary.run, 'native', arguments)

    # FastMCP's generated outer argument models default to extra=ignore. Tighten
    # only these two tools, including the published schema, before any session.
    for name in ('research_normalize_preview', 'research_native_preview'):
        tool = mcp._tool_manager.get_tool(name)
        tool.fn_metadata.arg_model.model_config.update(extra='forbid', strict=True)
        tool.fn_metadata.arg_model.model_rebuild(force=True)
        tool.parameters = tool.fn_metadata.arg_model.model_json_schema()


def create_preview_server(database: Path) -> FastMCP:
    mcp = FastMCP('LivingMath Read-only Preview008', json_response=True)
    mcp._mcp_server.version = '0.4.2-preview' + VERSION
    register_preview_tools(mcp, database)
    return mcp


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, required=True, help='Existing authorized schema5 database; never created/migrated')
    args = parser.parse_args()
    create_preview_server(args.db).run(transport='stdio')


if __name__ == '__main__':
    main()
