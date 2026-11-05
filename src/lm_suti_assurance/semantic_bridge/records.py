"""Strict application contracts; scientific admission stays in the frozen core."""
import json
from pathlib import Path
from jsonschema import Draft202012Validator
from ..core import digest
from ..errors import AssuranceError
from ..validation import inspect, parse

SCHEMAS = Path(__file__).parent / 'schemas'


def schema(name):
    return json.loads((SCHEMAS / (name + '.schema.json')).read_text())


def validate(name, value):
    inspect(value)
    expected = schema(name)
    if not isinstance(value, dict) or value.get('schema') != expected['properties']['schema']['const']:
        raise AssuranceError('MIGRATION_REQUIRED', '/schema')
    errors = sorted(Draft202012Validator(expected).iter_errors(value), key=lambda e:str(e.path))
    if errors:
        e = errors[0]
        raise AssuranceError('SEMANTIC_SCHEMA_INVALID', '/'+'/'.join(map(str,e.path)), {'validator': e.validator})
    if name not in ('proposal','package') and value['content_digest'] != digest({k:v for k,v in value.items() if k != 'content_digest'}):
        raise AssuranceError('OBJECT_DIGEST_MISMATCH')
    return value


def seal(name, project, source_digest, body, *, origin='DERIVED', producer=None,
         created_by='semantic-bridge/1', parents=()):
    value = {'schema':'lm-suti.semantic.'+name+'/1','schema_version':1,'project_id':project,
             'source_snapshot_digest':source_digest,'origin_kind':origin,
             'producer_ref':producer or digest({'component':'semantic-bridge/1'}),
             'created_by':created_by,'parent_refs':list(parents),'execution_permission':False,**body}
    value['content_digest'] = digest(value)
    return validate(name,value)


def proposal(raw):
    value = validate('proposal', parse(raw))
    ids = [v['id'] for v in value['literal_observations']+value['interpretations']]
    if len(ids) != len(set(ids)):
        raise AssuranceError('DUPLICATE_CLAIM_ID')
    relation_ids = [v['id'] for v in value['relations']]
    if len(relation_ids) != len(set(relation_ids)):
        raise AssuranceError('DUPLICATE_RELATION_ID')
    if any(r['from_claim'] not in ids or r['to_claim'] not in ids for r in value['relations']):
        raise AssuranceError('RELATION_CLAIM_NOT_FOUND')
    return value
