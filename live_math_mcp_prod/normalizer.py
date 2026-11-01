"""Read-only, source-preserving previews. A normal form is not a quotient or proof."""
from __future__ import annotations
import argparse
import copy
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time

import jsonschema
import tiktoken

VERSION = '004.1'
SCHEMA_PATH = Path(__file__).with_name('normalization-schema.json')
ENCODING = tiktoken.get_encoding('o200k_base')
RELATIONS = {'depends_on', 'contradicts', 'alias_candidate', 'refines', 'derived_from', 'requires_witness', 'independent_of'}
TYPES = {'SOURCE_CLAIM', 'HYPOTHESIS', 'EXPERIMENT_RESULT', 'COUNTEREXAMPLE', 'UNKNOWN', 'FORMAL_CLAIM', 'OPERATOR_DECISION'}
EVENT_PATTERN = re.compile(r'(?<!\w)event:([1-9]\d*)(?=\D|$)')
DIRECT = ('events', 'research_obligations', 'frontier_constraints', 'transformation_contracts', 'research_moves', 'adverse_evidence_reviews')
BY_MOVE = ('research_move_audits', 'research_move_status_history', 'research_move_bindings', 'research_move_request_keys')


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def auditor_fingerprint() -> str:
    names = ('research_store.py', 'frontier.py', 'evidence_review.py', 'move_lifecycle.py', 'mcp_server.py')
    return digest({name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() for name in names})


@dataclass(frozen=True)
class Budget:
    max_source_bytes: int = 4_000_000
    max_output_bytes: int = 1_000_000
    max_tokens: int = 100_000
    max_events: int = 2000
    max_milliseconds: int = 2000

    def __post_init__(self):
        if min(asdict(self).values()) <= 0 or self.max_output_bytes < 4096 or self.max_tokens < 1024:
            raise ValueError('Positive bounds; output>=4096 bytes and>=1024 estimated tokens required')


def read_history(path: Path | str, project: str, budget: Budget | None = None) -> dict:
    """Consistent SELECT-only snapshot; never creates, migrates or opens the source for writing."""
    budget = budget or Budget()
    source = Path(path).expanduser().resolve(strict=True)
    tables = {}
    started = time.perf_counter();consumed = 0
    def collect(cursor):
        nonlocal consumed
        result = []
        for row in cursor:
            value = dict(row);consumed += len(canonical(value).encode())
            if consumed > budget.max_source_bytes or time.perf_counter()-started > budget.max_milliseconds/1000:
                raise ValueError('Source snapshot byte/time bound exceeded; no partial context emitted')
            result.append(value)
        return result
    with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=budget.max_milliseconds/1000) as connection:
        connection.row_factory = sqlite3.Row
        connection.set_progress_handler(lambda: int(time.perf_counter()-started > budget.max_milliseconds/1000), 1000)
        connection.execute('PRAGMA query_only=ON');connection.execute('BEGIN')
        version = connection.execute('PRAGMA user_version').fetchone()[0]
        if version != 5:
            raise ValueError('Read-only preview supports existing schema5; no migration is performed')
        for name in DIRECT:
            tables[name] = collect(connection.execute('SELECT * FROM ' + name + ' WHERE project=? ORDER BY id', (project,)))
        if len(tables['events']) > budget.max_events:
            raise ValueError('Source event bound exceeded; no partial source is treated as complete')
        event_ids = {r['id'] for r in tables['events']}
        obligation_ids = {r['id'] for r in tables['research_obligations']}
        move_ids = {r['id'] for r in tables['research_moves']}
        selections = [('reviews', 'event_id', event_ids), ('research_obligation_versions', 'obligation_id', obligation_ids)]
        selections.extend((table, 'move_id', move_ids) for table in BY_MOVE)
        for name, column, ids in selections:
            if ids:
                tables[name] = collect(connection.execute('SELECT * FROM ' + name + ' WHERE ' + column + ' IN (' + ','.join('?' for _ in ids) + ')', sorted(ids)))
            else:
                tables[name] = []
        tables['policies'] = collect(connection.execute('SELECT * FROM policies ORDER BY code'))
        tables['frontier_imports'] = collect(connection.execute("SELECT * FROM frontier_imports WHERE json_extract(summary_json,'$.project')=?", (project,)))
    history = {'project': project, 'schema_version': version, 'tables': tables}
    if len(canonical(history).encode()) > budget.max_source_bytes:
        raise ValueError('Source byte bound exceeded')
    return history


def strict_json(text: str) -> tuple:
    """JSON only. Duplicate keys/nonfinite values remain ambiguous raw source."""
    def pairs(entries):
        result = {}
        for key, value in entries:
            if key in result:
                raise ValueError('Duplicate JSON key: ' + key)
            result[key] = value
        return result
    try:
        value = json.loads(text, object_pairs_hook=pairs, parse_constant=lambda s: (_ for _ in ()).throw(ValueError(s)))
        return value, 'EXACT_JSON' if isinstance(value, dict) else 'OPAQUE'
    except (ValueError, RecursionError):
        return None, 'AMBIGUOUS' if text.lstrip().startswith(('{', '[')) else 'OPAQUE'


def source_references(value: object, key: str = '') -> set:
    """Conservative finite dependency closure over declared references, not semantic inference."""
    found = set()
    if isinstance(value, dict):
        for name, entry in value.items():
            found |= source_references(entry, name)
    elif isinstance(value, list):
        for entry in value:
            if key.endswith('event_ids') and type(entry) is int:
                found.add(entry)
            else:
                found |= source_references(entry, key)
    elif type(value) is int and key in {'parent_id', 'event_id', 'source_event_id'}:
        found.add(value)
    elif isinstance(value, str):
        found.update(int(n) for n in EVENT_PATTERN.findall(value))
        if key.endswith('_json') or key == 'content':
            parsed, quality = strict_json(value)
            if quality == 'EXACT_JSON':
                found |= source_references(parsed)
    return found


def json_locations(text: str) -> dict:
    """Offsets in the original JSON characters, including the original escaped spelling."""
    decoder = json.JSONDecoder();locations = {}
    def skip(pos):
        while pos < len(text) and text[pos].isspace():
            pos += 1
        return pos
    def parse(pos, pointer, depth=0):
        if depth > 32:
            raise ValueError('JSON locator depth bound')
        pos = skip(pos);start = pos
        if text[pos] == '{':
            pos = skip(pos + 1)
            while text[pos] != '}':
                key, pos = decoder.raw_decode(text, pos)
                pos = skip(pos)
                if text[pos] != ':':
                    raise ValueError('Invalid JSON object')
                escaped = key.replace('~', '~0').replace('/', '~1')
                pos = skip(parse(pos + 1, pointer + '/' + escaped, depth + 1))
                if text[pos] == ',':
                    pos = skip(pos + 1)
                else:
                    break
            pos += 1
        elif text[pos] == '[':
            pos = skip(pos + 1);index = 0
            while text[pos] != ']':
                pos = skip(parse(pos, pointer + '/' + str(index), depth + 1));index += 1
                if text[pos] == ',':
                    pos = skip(pos + 1)
                else:
                    break
            pos += 1
        else:
            _, pos = decoder.raw_decode(text, pos)
        locations[pointer] = (start, pos)
        return pos
    parse(0, '')
    return locations


def audit_closure(history: dict, candidates: list, extra_roots: set | None = None) -> tuple:
    events = {row['id']: row for row in history['tables']['events']}
    required = source_references(candidates) | (extra_roots or set())
    for name, rows in history['tables'].items():
        if name != 'events':
            required |= source_references(rows)
    # Never silently drop adverse records, even outside the immediate focus.
    required.update(eid for eid, row in events.items() if row['kind'] in {'failure', 'failed_check', 'counterexample', 'rca'} or row['status'] in {'refuted', 'counterexample'})
    if any(not a.get('move') for a in candidates):
        required.update(events)  # Legacy audit reads project history; no selective optimization.
    seen = set()
    while required - seen:
        for eid in sorted(required - seen):
            seen.add(eid)
            if eid in events:
                required |= source_references(events[eid])
    return required, sorted(required - set(events))


def span(field: str, text: str, pointer: str = '') -> dict:
    return {'field': field, 'start': 0, 'end': len(text), 'json_pointer': pointer}


def concept(event: dict, history: dict) -> dict:
    raw = event['content'];parsed, quality = strict_json(raw)
    payload = parsed if quality == 'EXACT_JSON' else {}
    project, ref = history['project'], 'event:' + str(event['id'])
    source_ref = {'ref': ref, 'project': project, 'sha256': digest(event), 'span': span('content', raw)}
    unknowns = []
    for item in payload.get('unknowns', []) if isinstance(payload.get('unknowns', []), list) else []:
        unknowns.append({'field': 'source.unknowns', 'reason': item if isinstance(item, str) else canonical(item), 'source_ref': ref})
    fields = ('statement', 'scope', 'representation', 'version', 'claim_map', 'method_model', 'counter_reading',
              'premises', 'observables', 'alternatives', 'counterevidence', 'relations')
    for field in fields:
        if field not in payload or payload[field] is None:
            unknowns.append({'field': field, 'reason': 'Not reliably declared; canonical source retained', 'source_ref': ref})
    if quality != 'EXACT_JSON':
        unknowns.append({'field': 'content', 'reason': quality + ': opaque or ambiguous source, not parsed as a claim', 'source_ref': ref})
    claimed_type = payload.get('claim_type', 'UNKNOWN')
    claim_type = claimed_type if isinstance(claimed_type, str) and claimed_type in TYPES else 'UNKNOWN'
    if quality != 'EXACT_JSON':
        claim_type = 'UNKNOWN'
    state = 'refuted' if event['status'] in {'refuted', 'counterexample'} else 'observed' if event['status'] in {'observation', 'experiment'} else 'unverified'
    if isinstance(payload.get('epistemic_status'), str) and payload['epistemic_status'] in {'superseded', 'requires_review'}:
        state = payload['epistemic_status']
    if event['status'] == 'verified' or payload.get('epistemic_status') == 'verified_by_external_proof':
        state = 'unverified'
        unknowns.append({'field': 'epistemic_status', 'reason': 'External verification declaration retained, not validated or promoted', 'source_ref': ref})
    relations = []
    for relation in payload.get('relations', []) if isinstance(payload.get('relations', []), list) else []:
        if not isinstance(relation, dict) or not isinstance(relation.get('type'), str) or relation['type'] not in RELATIONS or not isinstance(relation.get('target_ref'), str):
            unknowns.append({'field': 'relations', 'reason': 'Undeclared or malformed relation retained in raw source', 'source_ref': ref})
            continue
        relations.append({'type': relation['type'], 'target_ref': relation['target_ref'], 'source_refs': [source_ref],
                          'assertion_status': 'SOURCE_DECLARED', 'substitution_allowed': False})
    method = payload.get('method_model') if isinstance(payload.get('method_model'), dict) else {}
    metadata = history['tables'].get('research_obligation_versions', [])
    current_versions = {o['id']: o['current_version'] for o in history['tables'].get('research_obligations', [])}
    obligations = []
    for row in metadata:
        declaration = json.loads(row['payload_json'])
        if (event['id'] in declaration.get('source_event_ids', [])
                and declaration['version'] == current_versions.get(declaration['id'])
                and declaration['status'] in {'OPEN', 'TESTING'}):
            obligations.append({k: declaration[k] for k in ('id', 'version', 'status', 'scope')})
    # Focus is always an exact source spelling with an exact field span, even for escaped JSON text.
    surfaces = [{'text': event['focus'], 'raw_literal': event['focus'], 'source_ref': ref, 'span': span('focus', event['focus'])}]
    try:
        locations = json_locations(raw) if quality == 'EXACT_JSON' else {}
    except (ValueError, RecursionError, IndexError):
        locations = {}
    for index, literal in enumerate(payload.get('surface_forms', []) if isinstance(payload.get('surface_forms', []), list) else []):
        if isinstance(literal, str):
            pointer = '/surface_forms/' + str(index)
            if pointer in locations:
                start, end = locations[pointer]
                surfaces.append({'text': literal, 'raw_literal': raw[start:end], 'source_ref': ref,
                    'span': {'field': 'content', 'start': start, 'end': end, 'json_pointer': pointer}})
    declared = {'project': project, 'source_sha256': digest(event), 'scope': payload.get('scope'),
                'representation': payload.get('representation'), 'version': payload.get('version'),
                'description': ' '.join(event['focus'].split())}
    return {'concept_id': 'concept:' + digest(declared), 'surface_forms': surfaces, 'claim_type': claim_type,
        'statement': payload.get('statement', raw), 'source_record': copy.deepcopy(event), 'source_refs': [source_ref],
        'premises': payload.get('premises', []) if isinstance(payload.get('premises', []), list) else [],
        'scope': payload.get('scope'), 'representation': payload.get('representation'), 'version': payload.get('version'),
        'claim_map': payload.get('claim_map'), 'method_model': {k: method.get(k) for k in ('input', 'operation', 'output')},
        'counter_reading': payload.get('counter_reading'), 'observables': payload.get('observables', []) if isinstance(payload.get('observables', []), list) else [],
        'alternatives': payload.get('alternatives', []) if isinstance(payload.get('alternatives', []), list) else [],
        'counterevidence': payload.get('counterevidence', []) if isinstance(payload.get('counterevidence', []), list) else [],
        'unknowns': unknowns, 'open_obligations': obligations, 'relations': relations, 'epistemic_status': state,
        'extraction_method': 'exact declared JSON fields; otherwise opaque source quotation', 'normalizer_version': VERSION,
        'input_hashes': [digest(event)], 'confidence': {'extraction_quality': quality, 'truth_probability': None},
        'loss_ledger': [{'source_ref': ref, 'change': 'Unmapped fields not interpreted; full original event retained', 'recovery': ref + '/content'}]}


class ContextNormalizer:
    def __init__(self):
        self.cache = {}

    def normalize(self, history: dict, focus: str, candidates: list, level: str = 'C2', budget: Budget | None = None) -> dict:
        budget = budget or Budget()
        start = time.perf_counter()
        if level not in {'C0', 'C1', 'C2', 'C3', 'C4'}:
            raise ValueError('Unknown level')
        if len(focus) > 4096 or len(candidates) > 256:
            raise ValueError('Focus/D_q input bound exceeded; no partial completeness claim')
        def refuse(reason, source_digest='UNAVAILABLE_INPUT_BOUND'):
            return {'schema_version': 1, 'normalizer_version': VERSION, 'project': history['project'], 'focus': focus,
                'level': level, 'status': 'INSUFFICIENT_CONTEXT', 'input_digest': source_digest,
                'source_catalog': {}, 'concepts': [], 'interpretations': [], 'audit_context': None,
                'coverage': {'registered': len(candidates), 'covered': 0, 'auditable': False},
                'unresolved': [reason], 'loss_ledger': [{'change': 'No source extraction after input bound refusal', 'recovery': 'Read explicitly with a larger bound'}],
                'certificate': {'candidate_hashes': [], 'context_digest': None, 'scope': 'No completeness claim'}, 'proof_status': 'unverified'}
        original_events = history['tables']['events']
        if len(original_events) > budget.max_events or sum(len(e['content']) for e in original_events) > budget.max_source_bytes:
            return refuse('Source input bound exceeded before extraction')
        if len(canonical(history).encode()) > budget.max_source_bytes:
            return refuse('Source byte bound exceeded before extraction')
        history = copy.deepcopy(history)
        for name, rows in history['tables'].items():
            rows.sort(key=canonical)
        source_digest = digest(history)
        schema_digest = hashlib.sha256(SCHEMA_PATH.read_bytes()).hexdigest()
        audit_digest = auditor_fingerprint()
        key = digest([source_digest, focus, candidates, level, asdict(budget), VERSION, schema_digest, audit_digest])
        if key in self.cache:
            return copy.deepcopy(self.cache[key])
        events = history['tables']['events']
        if any(e['project'] != history['project'] for e in events):
            raise ValueError('Cross-project source binding refused')
        catalog = {'event:' + str(e['id']): digest(e) for e in events}
        body = {'schema_version': 1, 'normalizer_version': VERSION, 'project': history['project'], 'focus': focus,
            'level': level, 'status': 'INSUFFICIENT_CONTEXT', 'input_digest': source_digest, 'source_catalog': catalog,
            'concepts': [], 'interpretations': [], 'audit_context': None,
            'coverage': {'registered': len(candidates), 'covered': 0, 'auditable': False},
            'unresolved': [], 'loss_ledger': [], 'certificate': {'candidate_hashes': [], 'context_digest': None,
                'schema_digest': schema_digest, 'auditor_code_digest': audit_digest,
                'scope': 'Only this finite registered family and auditor version; not a semantic completeness theorem.'},
            'proof_status': 'unverified'}
        lexical_roots = {e['id'] for e in events if e['focus'].casefold() in focus.casefold()}
        required, missing = audit_closure(history, candidates, lexical_roots)
        selected = set(catalog) if level in {'C0', 'C1'} else {'event:' + str(eid) for eid in required}
        selected_events = [e for e in events if 'event:' + str(e['id']) in selected]
        if len(canonical(history).encode()) > budget.max_source_bytes or len(events) > budget.max_events:
            body['unresolved'].append('Source input bound exceeded')
        if missing:
            body['unresolved'].append('Required project-local source missing: ' + ','.join(map(str, missing)))
        if not candidates:
            body['unresolved'].append('No registered D_q: preview only, no audit completeness certificate')
        if any(a.get('project', history['project']) != history['project'] for a in candidates):
            body['unresolved'].append('Candidate family contains a foreign project binding')
        local_obligations = {o['id'] for o in history['tables'].get('research_obligations', [])}
        if any(a.get('move', {}).get('active_frontier_id') is not None
               and a['move']['active_frontier_id'] not in local_obligations for a in candidates):
            body['unresolved'].append('Required project frontier missing or foreign')
        for e in events:
            if e not in selected_events:
                body['loss_ledger'].append({'source_ref': 'event:' + str(e['id']), 'sha256': digest(e),
                    'change': 'Outside registered audit dependency closure; source not deleted', 'recovery': 'Read original project event by ID/hash'})
        context = copy.deepcopy(history);context['tables']['events'] = selected_events
        if level != 'C0':
            body['concepts'] = [concept(e, history) for e in selected_events]
            # Lexical matches are hypotheses only and preserve both distinct source identities.
            for i, left in enumerate(body['concepts']):
                for right in body['concepts'][i + 1:]:
                    if left['surface_forms'][0]['text'] == right['surface_forms'][0]['text']:
                        body['interpretations'].append({'relation': 'alias_candidate', 'assertion_status': 'HYPOTHESIS',
                            'source_refs': left['source_refs'] + right['source_refs'], 'substitution_allowed': False,
                            'statement': 'Lexical coincidence only; entities and mathematical objects are not identified.'})
        if level == 'C4':
            for node in body['concepts']:
                original = node['source_record']
                node['source_record'] = {key: original[key] for key in ('id', 'project', 'kind', 'focus', 'status')}
                node['loss_ledger'].append({'source_ref': node['source_refs'][0]['ref'],
                    'change': 'C4 hides inline source content; exact span/hash remains recoverable from C0',
                    'recovery': node['source_refs'][0]['ref'] + '/content'})
                text = node['statement'] if isinstance(node['statement'], str) else canonical(node['statement'])
                if len(text) > 240:
                    node['statement'] = {'derived_preview': text[:240], 'source_ref': node['source_refs'][0]['ref']}
            body['status'] = 'EXPLANATION_ONLY'
            body['loss_ledger'].append({'change': 'C4 omits the audit payload and cannot replace C0', 'recovery': 'Request C0-C3 with the same source hashes and D_q'})
        elif not body['unresolved']:
            body['audit_context'] = context
            body['status'] = 'COMPLETE'
            body['coverage'] = {'registered': len(candidates), 'covered': len(candidates), 'auditable': True}
            body['certificate']['candidate_hashes'] = sorted(digest(a) for a in candidates)
            body['certificate']['context_digest'] = digest(context)
        used = canonical(body)
        if (len(used.encode()) > budget.max_output_bytes or len(ENCODING.encode(used, disallowed_special=())) > budget.max_tokens
                or 1000 * (time.perf_counter() - start) > budget.max_milliseconds):
            body.update(status='INSUFFICIENT_CONTEXT', concepts=[], interpretations=[], audit_context=None,
                        source_catalog={}, unresolved=['Output/time budget cannot preserve the registered audit closure'],
                        loss_ledger=[{'change': 'No partial permission-bearing view emitted', 'recovery': 'Retry explicitly with a larger budget and original source digest'}])
            body['coverage'] = {'registered': len(candidates), 'covered': 0, 'auditable': False}
            body['certificate'].update(candidate_hashes=[], context_digest=None)
        jsonschema.validate(body, json.loads(SCHEMA_PATH.read_text()))
        if len(self.cache) >= 8:
            self.cache.pop(next(iter(self.cache)))
        self.cache[key] = copy.deepcopy(body)
        return body


def normalize_context(history: dict, focus: str, candidates: list, level: str = 'C2', budget: Budget | None = None) -> dict:
    return ContextNormalizer().normalize(history, focus, candidates, level, budget)


def reconstruct_context(view: dict, source_history: dict) -> dict:
    """Lazy recovery from the retained canonical source; reject version/hash drift."""
    source = copy.deepcopy(source_history)
    for rows in source['tables'].values():
        rows.sort(key=canonical)
    if view['input_digest'] != digest(source) or view['audit_context'] is None:
        raise ValueError('Source changed or projection is not independently reconstructible')
    recovered = copy.deepcopy(view['audit_context'])
    available = {e['id']: e for e in source['tables']['events']}
    selected = {e['id']: e for e in recovered['tables']['events']}
    for ref, checksum in view['source_catalog'].items():
        eid = int(ref.split(':')[1])
        original = available.get(eid)
        if original is None or digest(original) != checksum:
            raise ValueError('Unresolvable source pointer/hash')
        if eid in selected and selected[eid] != original:
            raise ValueError('Projection changed a canonical event')
        selected[eid] = copy.deepcopy(original)
    recovered['tables']['events'] = list(selected.values())
    for rows in recovered['tables'].values():
        rows.sort(key=canonical)
    if digest(recovered) != view['input_digest']:
        raise ValueError('Metadata or source recovery mismatch')
    return recovered


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['preview'])
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--project', required=True)
    parser.add_argument('--focus', default='Research context preview')
    parser.add_argument('--dq', type=Path)
    parser.add_argument('--level', choices=['C0', 'C1', 'C2', 'C3', 'C4'], default='C2')
    parser.add_argument('--budget-tokens', type=int, default=100000)
    args = parser.parse_args()
    budget = Budget(max_tokens=args.budget_tokens)
    history = read_history(args.db, args.project, budget)
    candidates = json.loads(args.dq.read_text()) if args.dq else []
    print(json.dumps(normalize_context(history, args.focus, candidates, args.level, budget), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
