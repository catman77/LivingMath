"""Intake of author-supplied working files under explicit user-session authority.

This records the actual permission channel; it does not invent an author
signature, a formal software release, or a live SUTI export API.
"""
import json
from pathlib import Path
from zipfile import ZipFile

from .shared import Refusal, bytes_hash, canonical_bytes, canonical_hash, statuses
from .ingest import immutable_write

MEMBER = 'SUTI.uni/SUTI.game/algorithm-contour.v1.md'


def archive_hash(path: Path) -> str:
    import hashlib
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def ingest_working_source(archive: Path, member: str, authorization: dict,
                          state: Path, request_key: str) -> tuple[dict, bytes]:
    digest = archive_hash(archive)
    if (authorization.get('channel') != 'ACTIVE_USER_SESSION'
            or authorization.get('author_supplied_archives_reported_by_user') is not True
            or not {'local_read', 'local_analysis', 'development', 'isolated_qa'} <= set(authorization.get('scope', []))
            or digest not in authorization.get('archive_sha256', [])
            or not authorization.get('statement', '').strip()):
        raise Refusal('USER_SESSION_AUTHORIZATION_REQUIRED')
    if authorization.get('statement_sha256') != bytes_hash(authorization['statement'].encode()):
        raise Refusal('AUTHORIZATION_STATEMENT_DRIFT')
    if not request_key or len(request_key) > 128:
        raise Refusal('INVALID_REQUEST_KEY')
    with ZipFile(archive) as container:
        entries = [info for info in container.infolist() if info.filename == member]
        if len(entries) != 1 or entries[0].is_dir() or entries[0].file_size > 4_000_000:
            raise Refusal('MISSING_AMBIGUOUS_OR_OVERSIZED_WORKING_MEMBER')
        with container.open(entries[0]) as stream:
            raw = stream.read(4_000_001)
    if not raw or len(raw) > 4_000_000:
        raise Refusal('WORKING_SOURCE_BYTE_BOUND')
    raw.decode('utf-8')
    snapshot = {'source_kind': 'AUTHOR_SUPPLIED_SUTI_WORKING_DOCUMENT',
                'archive_name': archive.name, 'archive_sha256': digest, 'member': member,
                'source_sha256': bytes_hash(raw), 'bytes': len(raw),
                'revision_basis': 'ACTUAL_WORKING_BYTES_SHA256',
                'authorization_sha256': canonical_hash(authorization),
                'origin_basis': 'User states these archives were supplied by SUTI author.',
                'SUTI_runtime_executed': False, 'formal_release_required': False,
                'author_signature_claimed': False,
                **statuses(semantic='AWAITING_SOURCE_LOCAL_MAPPING', execution='WORKING_BYTES_IMPORTED')}
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    if state.stat().st_mode & 0o077:
        raise Refusal('PRIVATE_WORKING_STATE_REQUIRED')
    intent = canonical_hash(snapshot)
    key_path = state / (bytes_hash(request_key.encode()) + '.request.json')
    if key_path.exists() and json.loads(key_path.read_text())['intent_sha256'] != intent:
        raise Refusal('REQUEST_KEY_SOURCE_OR_AUTHORIZATION_CONFLICT')
    immutable_write(state / (snapshot['source_sha256'] + '.raw'), raw)
    immutable_write(state / (intent + '.snapshot.json'), canonical_bytes(snapshot))
    immutable_write(key_path, canonical_bytes({'request_key': request_key, 'intent_sha256': intent}))
    return snapshot, raw


def address(raw: bytes, quote: str) -> dict:
    text = raw.decode('utf-8')
    if text.count(quote) != 1:
        raise Refusal('SOURCE_SELECTOR_MISSING_OR_AMBIGUOUS', quote)
    start = text.index(quote);end = start + len(quote)
    return {'source_sha256': bytes_hash(raw), 'start': start, 'end': end,
            'byte_start': len(text[:start].encode()), 'byte_end': len(text[:end].encode()), 'quote': quote}


def source_contract(raw: bytes, snapshot: dict) -> dict:
    if bytes_hash(raw) != snapshot['source_sha256'] or len(raw) != snapshot['bytes']:
        raise Refusal('WORKING_SOURCE_DRIFT')
    definitions = [
        ('D', 'D_MENU_BUDGET', 'make_options(max_count=3, include=["pause", "skip", "exit"])', 'At most three menu options; counting scope must be explicit.'),
        ('D', 'D_CONTROL_PRESENCE', '5. предложить максимум 3 варианта хода, включая pause / skip / exit', 'Pause, skip and exit are available choices.'),
        ('D', 'D_EXPLICIT_CHOICE', '6. ждать явного выбора; молчание = не действие и не согласие', 'Silence never acts or consents.'),
        ('D', 'D_TRIAL_BRANCH', 'result = execute_reversible_trial(chosen)', 'A non-control explicit choice leads to a reversible trial.'),
        ('D', 'D_OUTCOME', '8. спросить о наблюдаемом последствии; не выводить его автоматически', 'Outcome is reported, not inferred by the model.'),
        ('D', 'D_SAVE', '10. предложить сохранить короткий след; по умолчанию не сохранять', 'Saving requires a separate explicit choice.'),
        ('R', 'R_CONTROL_BRANCH', 'if chosen in ["pause", "skip", "exit"]:\n        return finish_or_pause_without_score(chosen)', 'Control choices do not execute the trial branch.'),
        ('T', 'T_CHOOSE_THEN_TRIAL', 'chosen = wait_for_explicit_choice(options)', 'Choice precedes trial execution.'),
        ('T', 'T_REPORT_THEN_SAVE', 'observation = ask_person_what_happened(result)\n    usefulness = ask_person_if_helpful(observation)\n    trace = ask_before_save(minimal_trace(observation, usefulness))', 'Report precedes optional save.'),
        ('O', 'O_SELECTABLE_TRIAL', '7. выполнить только обратимую пробу, выбранную человеком', 'Question: does the declared menu admit any trial choice?'),
        ('O', 'O_AUTHOR_REVIEW', 'NEXT`: отдельный авторский design review этой спецификации', 'Recognition of this interpretation requires actual author feedback.'),
    ]
    result = {'source_sha256': snapshot['source_sha256'], 'source_ref': snapshot['member'],
              'scope': 'Source-local choice menu, explicit action, outcome and save clauses; remaining document retained raw and not formalized.',
              'X': {'sha256': snapshot['source_sha256'], 'bytes': len(raw), 'mime_type': 'text/markdown'},
              'D': [], 'R': [], 'T': [], 'O': [],
              'P': {'archive_sha256': snapshot['archive_sha256'], 'authorization_sha256': snapshot['authorization_sha256'],
                    'basis': 'Working files and explicit user authorization; no release or author signature required for local work.'}}
    for section, identifier, quote, statement in definitions:
        result[section].append({'id': identifier, 'source_address': address(raw, quote), 'statement': statement,
                                'must_preserve': section != 'O'})
    return result
