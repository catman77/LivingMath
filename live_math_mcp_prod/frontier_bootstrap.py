"""Import explicit scoped RH frontier records, guarded by original event hashes."""
import argparse
import json
from pathlib import Path
import sqlite3

from frontier import fingerprint_hash
from research_store import ResearchStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True)
    parser.add_argument('--blueprint', default=str(Path(__file__).parent / 'testdata/rh_frontier_seed.json'))
    parser.add_argument('--operator', required=True)
    parser.add_argument('--apply', action='store_true', help='apply after source-hash validation; default is read-only')
    args = parser.parse_args()
    path = Path(args.db).expanduser().resolve(strict=True)
    blueprint = json.loads(Path(args.blueprint).read_text())
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as connection:
        connection.row_factory = sqlite3.Row
        for source in blueprint['sources']:
            row = connection.execute('SELECT * FROM events WHERE id=?', (source['id'],)).fetchone()
            if row is None or row['project'] != blueprint['project'] or fingerprint_hash(dict(row)) != source['sha256']:
                raise SystemExit('Original source-event hash mismatch: ' + str(source['id']))
    if args.apply:
        result = ResearchStore(path).frontier.import_history(blueprint, args.operator)
    else:
        result = {'mode': 'read_only_preflight', 'source_hashes_match': True,
                  'obligations_to_import': len(blueprint['obligations']),
                  'constraints_to_import': len(blueprint['constraints'])}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
