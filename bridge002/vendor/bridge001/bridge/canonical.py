"""Bounded canonical JSON profile: UTF-8, sorted keys, finite JSON numbers."""
import hashlib
import json

MAX_BYTES = 262144


class Refusal(ValueError):
    def __init__(self, code: str, detail: str = ''):
        self.code, self.detail = code, detail
        super().__init__(code + (': ' + detail if detail else ''))


def canonical_bytes(value) -> bytes:
    def walk(x, depth=0):
        if depth > 32:
            raise Refusal('DEPTH_LIMIT')
        if isinstance(x, dict):
            if not all(isinstance(k, str) for k in x):
                raise Refusal('JSON_STRING_KEYS_REQUIRED')
            for v in x.values():
                walk(v, depth + 1)
        elif isinstance(x, list):
            for v in x:
                walk(v, depth + 1)
    walk(value)
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(',', ':'), allow_nan=False).encode('utf-8')
    except (ValueError, TypeError, UnicodeError) as error:
        raise Refusal('NON_CANONICAL_JSON', str(error)) from error


def canonical_hash(value) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def bytes_hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_json(path):
    raw = path.read_bytes()
    if len(raw) > MAX_BYTES:
        raise Refusal('INPUT_BYTE_LIMIT')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise Refusal('DUPLICATE_JSON_KEY', key)
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=unique,
                          parse_constant=lambda x: (_ for _ in ()).throw(Refusal('NON_FINITE_JSON', x)))
    except (json.JSONDecodeError, UnicodeError) as error:
        raise Refusal('INVALID_JSON', str(error)) from error


def statuses(semantic='NOT_ASSESSED', mathematical='NOT_TESTED', execution='NOT_EXECUTED',
             author='NO_REVIEW', provenance=None, unknowns=None):
    return {'semantic_status': semantic, 'mathematical_status': mathematical,
            'execution_status': execution, 'author_review_status': author,
            'proof_status': 'unverified', 'execution_permission': {'allowed': False},
            'source_provenance': provenance or {}, 'unknowns': unknowns or []}
