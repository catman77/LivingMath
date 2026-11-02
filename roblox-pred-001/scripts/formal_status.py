"""Read the real background experiment state; never advances its lifecycle."""
import argparse
from collections import Counter
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    run = args.run_dir or Path(json.loads((root / 'reports/formal-run.json').read_text())['run_directory'])
    status = json.loads((run / 'status.json').read_text())
    results = [json.loads(path.read_text()) for path in (run / 'cases').glob('*/result.json')]
    status.update(
        semantic_available_completed=sum(r['semantic_available'] for r in results),
        formal_available_completed=sum(r['formal_available'] for r in results),
        completed_model_statuses=dict(Counter(s for r in results for s in r.get('model_statuses', []))),
        report_exists=(run / 'report.md').exists(),
        comparison_exists=(run / 'comparison.json').exists(),
    )
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
