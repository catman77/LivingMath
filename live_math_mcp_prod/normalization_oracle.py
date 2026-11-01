"""Independent finite expectation rules and the actual unmodified SQLite auditor."""
import copy
import json
from pathlib import Path
import sqlite3

from normalizer import canonical, digest, auditor_fingerprint
from research_store import ResearchStore


def expected(candidate: dict) -> dict:
    """Separate rule model; no call to the normalizer or deployed audit implementation."""
    p = candidate['oracle_parameters'];codes = set()
    if p['branch'] == 'closed':
        codes.add('OBSOLETE_FRONTIER')
    accepted_diagnostic = (p['branch'] == 'active' and p['diagnostic'] and p['review_current'])
    if p['adverse'] and not accepted_diagnostic:
        codes.add('ADVERSE_EVIDENCE_REQUIRES_REVIEW')
    if p.get('historical_duplicate'):
        codes.add('NO_NEW_DISTINCTION')
    if p['transform']:
        if not p.get('contract'):
            codes.add('MISSING_TRANSFORMATION_CONTRACT')
        elif p['contract'] == 'mismatch':
            codes.add('TRANSFORMATION_CONTRACT_MISMATCH')
        codes.update({'UNPROVEN_SEMANTIC_PRESERVATION', 'REQUIRES_SEMANTIC_REVIEW'})
        if p['branch'] in {'active', 'independent'}:
            codes.add('EXPERIMENT_SCOPE_REQUIRES_REVIEW')
    if p['branch'] == 'open' and not codes:
        codes.add('REQUIRES_SEMANTIC_REVIEW')
    return {'verdict': 'REQUIRES_SEMANTIC_REVIEW' if codes else 'EXPERIMENT_ALLOWED',
            'codes': sorted(codes), 'execution_allowed': False, 'proof_status': 'unverified'}


def materialize(history: dict, destination: Path) -> ResearchStore:
    if destination.exists():
        raise ValueError('Temporary materialization must be a new database')
    store = ResearchStore(destination)
    # Only this new synthetic database is written. Canonical history is a detached immutable value.
    with sqlite3.connect(destination) as connection:
        connection.execute('PRAGMA foreign_keys=OFF')
        connection.execute('DELETE FROM policies')
        for table, rows in history['tables'].items():
            for row in rows:
                names = list(row)
                connection.execute('INSERT INTO ' + table + '(' + ','.join(names) + ') VALUES (' + ','.join('?' for _ in names) + ')', [row[n] for n in names])
    return store


def run_audit(store: ResearchStore, candidate: dict) -> dict:
    try:
        result = store.audit(candidate['project'], candidate['proposal'], **candidate['move'])
        active = store.frontier.inspect(candidate['project'], True)
        relevant = next((o for o in active['obligations'] if o['id'] == candidate['move'].get('active_frontier_id')), None)
        # Exact outputs include grounds, hashes, roles, reopening conditions and versions.
        return {'status': 'AUDITED', 'report': result,
                'scope': relevant['scope'] if relevant else None,
                'version': relevant['version'] if relevant else None}
    except ValueError as error:
        return {'status': 'INVALID_REFERENCE', 'reason': str(error), 'execution_allowed': False, 'proof_status': 'unverified'}


def projection_ready(view: dict, candidate: dict, original: dict) -> bool:
    """Validate provenance/metadata against the original registered source, not cached verdicts."""
    if view['status'] != 'COMPLETE' or view['level'] == 'C4' or view['audit_context'] is None:
        return False
    if view['certificate'].get('auditor_code_digest') != auditor_fingerprint():
        return False
    if digest(candidate) not in view['certificate']['candidate_hashes']:
        return False
    normalized_original = copy.deepcopy(original)
    for rows in normalized_original['tables'].values():
        rows.sort(key=canonical)
    if view['input_digest'] != digest(normalized_original):
        return False
    context = view['audit_context']
    if digest(context) != view['certificate']['context_digest'] or context['project'] != candidate['project']:
        return False
    source_events = {e['id']: e for e in original['tables']['events']}
    projected = {e['id']: e for e in context['tables']['events']}
    if any(source_events.get(i) != row for i, row in projected.items()):
        return False
    # All non-event audit inputs must be retained byte-for-value, including closed branches/dispositions.
    for name, rows in normalized_original['tables'].items():
        if name != 'events' and context['tables'].get(name) != rows:
            return False
    # Independently check that explicit candidate references and ancestor links remain resolvable.
    needed = set(candidate['move'].get('parent_event_ids', []))
    def walk(value):
        import re
        if isinstance(value, dict):
            for item in value.values():walk(item)
        elif isinstance(value, list):
            for item in value:walk(item)
        elif isinstance(value, str):
            needed.update(int(x) for x in re.findall(r'event:([1-9]\d*)', value))
    walk(candidate['move'])
    seen = set()
    while needed - seen:
        for eid in needed - seen:
            seen.add(eid)
            if eid not in projected:
                return False
            parent = projected[eid]['parent_id']
            if parent is not None:
                needed.add(parent)
    # Adverse records can never vanish merely to satisfy a budget.
    adverse = {i for i, e in source_events.items() if e['kind'] in {'failure', 'failed_check', 'counterexample', 'rca'} or e['status'] in {'refuted', 'counterexample'}}
    return adverse <= set(projected)


def audit_projection(store: ResearchStore | None, view: dict, candidate: dict, original: dict) -> dict:
    if not projection_ready(view, candidate, original) or store is None:
        return {'status': 'INSUFFICIENT_CONTEXT', 'execution_allowed': False, 'proof_status': 'unverified'}
    return run_audit(store, candidate)
