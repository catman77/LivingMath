"""Private child entry point. Limits precede mathematical imports and SQLite access."""
import json
import math
from pathlib import Path
import resource
import sys
import time


def main() -> None:
    start, cpu = time.perf_counter_ns(), time.process_time_ns()
    path, kind, memory_mb, deadline_ms = sys.argv[1:]
    memory_mb, deadline_ms = int(memory_mb), int(deadline_ms)
    resource.setrlimit(resource.RLIMIT_AS, (memory_mb * 1024**2, memory_mb * 1024**2))
    seconds = max(1, math.ceil(deadline_ms / 1000))
    resource.setrlimit(resource.RLIMIT_CPU, (seconds, seconds + 1))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    data = sys.stdin.buffer.read(65537)
    if len(data) > 65536:
        raise ValueError('Input byte limit')
    from native_preview008_contract import refusal
    try:
        from native_preview008_engine import evaluate, install_readonly_sqlite
        install_readonly_sqlite(Path(path))
        out = evaluate(Path(path), kind, json.loads(data))
    except MemoryError:
        out = refusal('RESOURCE_LIMIT', 'WORKER_MEMORY_BOUND')
    except Exception as error:
        out = refusal('INSUFFICIENT_CONTEXT', type(error).__name__ + ':' + str(error)[:200])
    out['worker_total_wall_ns'] = time.perf_counter_ns() - start
    out['worker_total_cpu_ns'] = time.process_time_ns() - cpu
    out['worker_max_rss_KiB'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    sys.stdout.write(json.dumps(out, ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
