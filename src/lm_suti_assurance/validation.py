"""Transport validation is separate from scientific admission."""
import json
from pathlib import Path
from jsonschema import Draft202012Validator
from .core import canonical, strict_json
from .errors import AssuranceError

MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_DEPTH = 48
SCHEMAS = Path(__file__).parent / 'schemas'


def parse(raw):
    if not isinstance(raw, str):
        raise AssuranceError('JSON_TEXT_REQUIRED')
    if len(raw.encode('utf-8')) > MAX_JSON_BYTES:
        raise AssuranceError('INPUT_TOO_LARGE')
    try:
        value = strict_json(raw)
        inspect(value)
        return value
    except AssuranceError:
        raise
    except (ValueError, TypeError, RecursionError) as exc:
        code = ('DUPLICATE_JSON_KEY' if 'DUPLICATE_JSON_KEY' in str(exc) else
                'NONFINITE_JSON' if 'NONFINITE_JSON' in str(exc) else 'INVALID_JSON')
        raise AssuranceError(code) from None


def inspect(value, depth=0):
    if depth > MAX_DEPTH:
        raise AssuranceError('JSON_DEPTH_EXCEEDED')
    if isinstance(value, dict):
        if any(not isinstance(k, str) for k in value):
            raise AssuranceError('JSON_STRING_KEYS_REQUIRED')
        for v in value.values():
            inspect(v, depth + 1)
    elif isinstance(value, list):
        for v in value:
            inspect(v, depth + 1)
    elif value is not None and type(value) not in (str, int, float, bool):
        raise AssuranceError('JSON_TYPE_REQUIRED')
    try:
        if depth == 0 and len(canonical(value).encode()) > MAX_JSON_BYTES:
            raise AssuranceError('INPUT_TOO_LARGE')
    except (ValueError, OverflowError):
        raise AssuranceError('NONFINITE_JSON') from None


def validate(name, value):
    inspect(value)
    schema = json.loads((SCHEMAS / (name + '.schema.json')).read_text())
    if not isinstance(value, dict) or value.get('schema') != schema['properties']['schema']['const']:
        raise AssuranceError('MIGRATION_REQUIRED', '/schema', {'expected': schema['properties']['schema']['const']})
    errors = sorted(Draft202012Validator(schema).iter_errors(value), key=lambda e: str(e.path))
    if errors:
        e = errors[0]
        raise AssuranceError('SCHEMA_VALIDATION_FAILED', '/' + '/'.join(map(str, e.path)),
                             {'validator': e.validator, 'message': e.message})
    return value


def safe_source_schema(source):
    """Frozen checker may validate embedded schemas; disallow external resolution.

    This is a transport boundary, not an alternative JSON Schema evaluator.
    Even local references are held in this finite preview to avoid recursive schemas.
    """
    if source.get('kind') != 'schema':
        return
    schema = parse(source['content_utf8'])
    # This preview admits only the two existing reviewed SUTI schema sources.
    # It is not a safe execution service for arbitrary regex/schema programs.
    from . import core
    trusted = json.loads((core.ROOT/'examples/SOURCE_SNAPSHOTS.json').read_text())
    registered = {v['sha256'] for v in trusted.values() if v.get('kind') == 'schema'}
    def walk(node):
        if isinstance(node, dict):
            if any(k in node for k in ('$ref', '$dynamicRef', '$recursiveRef')):
                raise AssuranceError('SCHEMA_REFERENCE_NOT_SUPPORTED', '/snapshot/content_utf8')
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
    walk(schema)
    if source.get('sha256') not in registered:
        raise AssuranceError('UNREGISTERED_SOURCE_SCHEMA', '/snapshot/sha256')
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        from jsonschema.exceptions import SchemaError
        if isinstance(exc, SchemaError):
            raise AssuranceError('INVALID_SOURCE_SCHEMA') from None
        raise
