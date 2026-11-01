"""Replay T1–T4 against existing sourced frontier records without writing to the ledger."""
import argparse
import copy
import json
from pathlib import Path
import sqlite3

from frontier import fingerprint_hash
from research_store import ResearchStore


def regression_requests(frontier):
    active = next(item['id'] for item in frontier['obligations']
                  if item['source_event_ids'] == [15] and item['status'] in ('OPEN', 'TESTING'))
    blueprint = json.loads((Path(__file__).parent / 'testdata/rh_frontier_seed.json').read_text())
    base = {'active_frontier_id': active, 'parent_event_ids': [15],
            'proposed_operation': {'mechanism': 'theta_edge_address_match', 'intent': 'experiment',
                'premises': ['actual T49/T54 theta edges'],
                'mathematical_properties': ['source_address and origin_id matching'],
                'testable_consequence': 'detect unmatched edges before comparing contributions',
                'required_evidence': ['source-address matching report']},
            'source_representation': 'actual_theta_source_edges',
            'target_representation': 'actual_theta_source_edges',
            'verification_plan': {'method': 'compare source_address and origin_id',
                                  'failure_condition': 'any unmatched source edge'}}
    x4 = copy.deepcopy(base)
    x4['parent_event_ids'] = [9]
    x4['proposed_operation']['mechanism'] = 'X4'
    rename = copy.deepcopy(base)
    rename['parent_event_ids'] = [14]
    rename['proposed_operation'] = copy.deepcopy(blueprint['moves'][0]['proposed_operation'])
    rename['proposed_operation']['display_name'] = 'New route extent'
    rename['proposed_operation']['mechanism'] = 'renamed_extent'
    rename['proposed_operation']['mathematical_properties'][0] = 'path length'
    erasure = copy.deepcopy(base)
    erasure['parent_event_ids'] = [13]
    erasure['proposed_operation'].update(mechanism='erase_point_loop', intent='transformation')
    erasure['target_representation'] = 'theta_edges_after_point_loop_erasure'
    erasure['preserved_properties'] = {'point_value': {'claim': 'preserved', 'evidence_refs': ['event:13']}}
    return [
        ('T1', 'OBSOLETE_FRONTIER', x4),
        ('T2', 'NO_NEW_DISTINCTION', rename),
        ('T3', 'UNPROVEN_SEMANTIC_PRESERVATION', erasure),
        ('T4', 'ACTIVE_CONTINUATION', base),
    ]


def run(store):
    with store._connect() as connection:
        before = {table: [dict(row) for row in connection.execute('SELECT * FROM ' + table + ' ORDER BY id')]
                  for table in ('events', 'operations')}
    frontier = store.frontier.inspect('RH', include_closed=True)
    rows = []
    for name, expected, request in regression_requests(frontier):
        report = store.audit('RH', name + ' actual-history regression', **request)
        assert report['classification'] == expected, (name, report['classification'])
        assert report['proof_status'] == 'unverified'
        assert report['verdict'] == ('EXPERIMENT_ALLOWED' if name == 'T4' else 'REQUIRES_SEMANTIC_REVIEW')
        rows.append({'test': name, 'request': request, 'result': report})
    with store._connect() as connection:
        after = {table: [dict(row) for row in connection.execute('SELECT * FROM ' + table + ' ORDER BY id')]
                 for table in ('events', 'operations')}
    assert before == after, 'A read-only audit changed research history.'
    return {'tests': rows, 'distinct_classifications': len({row['result']['classification'] for row in rows}),
            'event_rows_sha256': fingerprint_hash(after['events']),
            'audit_rows_sha256': fingerprint_hash(after['operations']),
            'audit_is_read_only': True, 'mathematical_results_verified': False, 'result': 'PASS'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    path = Path(args.db).expanduser().resolve(strict=True)
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as connection:
        if connection.execute('PRAGMA user_version').fetchone()[0] != 5:
            raise SystemExit('Migrate explicitly before running this read-only regression.')
    result = run(ResearchStore(path))
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'result': result['result'], 'distinct_classifications': result['distinct_classifications'],
                      'audit_is_read_only': True}, ensure_ascii=False))
