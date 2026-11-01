"""Exact JSON Schema admission and projection witnesses for registered real SUTI schemas."""
import hashlib
import json
from typing import Any
from urllib.parse import quote, unquote, urlparse

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012


def check(bundle: dict, pair_id: str, records: list[dict] | None, fields: list[str] | None) -> dict:
    pair = next((p for p in bundle['pairs'] if p['id'] == pair_id), None)
    if pair is None:
        raise ValueError('UNREGISTERED_SUTI_SOURCE_ID')
    member = pair['member']
    original = bundle['schema_members'][member]
    if hashlib.sha256(original['text'].encode()).hexdigest() != pair['source_sha256']:
        raise ValueError('SOURCE_HASH_DRIFT')
    schema = json.loads(original['text'])
    Draft202012Validator.check_schema(schema)
    records = pair['records'] if records is None else records
    fields = pair['observer']['fields'] if fields is None else fields
    if any(field not in schema.get('properties', {}) for field in fields):
        raise ValueError('PROJECTION_FIELD_NOT_IN_SOURCE_SCHEMA')
    if len(fields) != len(set(fields)) or not fields:
        raise ValueError('NONEMPTY_DISTINCT_PROJECTION_FIELDS_REQUIRED')
    if not 1 <= len(records) <= 4 or len(json.dumps(records).encode()) > 64000:
        raise ValueError('RECORD_BYTE_OR_COUNT_BOUND')
    origin = 'https://offline-source.invalid/'+pair['archive_sha256']+'/'
    base = origin+quote(member,safe='/')
    reached = {member}

    def retrieve(uri):
        if not uri.startswith(origin):
            raise ValueError('FOREIGN_OR_NETWORK_REFERENCE_REFUSED')
        target = unquote(urlparse(uri).path[len(urlparse(origin).path):])
        if target not in bundle['schema_members']:
            raise ValueError('UNREVIEWED_SCHEMA_REFERENCE')
        reached.add(target)
        doc = json.loads(bundle['schema_members'][target]['text'])
        return Resource.from_contents(doc, default_specification=DRAFT202012)
    resource = Resource.from_contents(schema)
    # referencing's attrs-generated constructor accepts retrieve; its installed typing omits that keyword.
    registry_factory: Any = Registry
    registry = registry_factory(retrieve=retrieve).with_resource(base,resource)
    resolver = registry.resolver(base).in_subresource(resource)
    validator = Draft202012Validator(schema,registry=registry,_resolver=resolver,format_checker=FormatChecker())
    results = []
    for index, record in enumerate(records):
        errors = list(validator.iter_errors(record))[:30]
        results.append({'record_index': index, 'valid': not errors, 'errors': [
            {'path': list(e.absolute_path), 'schema_path': list(e.absolute_schema_path), 'reason': e.message[:1000]} for e in errors]})
    projection = [{key: row.get(key) for key in fields} for row in records]
    presence = [{key: key in row for key in fields} for row in records]
    canonical = lambda obj: json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=False)
    collisions = [{'left_index':i,'right_index':j,'observed_equal':True,'source_records_equal':False,
                   'different_source_fields':sorted(k for k in set(records[i])|set(records[j]) if (k in records[i]) != (k in records[j]) or canonical(records[i].get(k)) != canonical(records[j].get(k)))}
        for i in range(len(records)) for j in range(i+1,len(records))
        if results[i]['valid'] and results[j]['valid'] and canonical([projection[i],presence[i]])==canonical([projection[j],presence[j]]) and canonical(records[i])!=canonical(records[j])]
    return {'status':'SCHEMA_VALIDATED','source_id':pair_id,'archive':pair['archive_name'],
        'archive_sha256':pair['archive_sha256'],'member':member,'source_sha256':pair['source_sha256'],
        'schema_dialect':schema.get('$schema'),'records':records,'record_checks':results,'projection_fields':fields,
        'projected_values':projection,'projection_presence':presence,'projection_collisions':collisions,'applicable_members':sorted(reached),
        'scope':'Complete record admission under these exact source schemas; no SUTI runtime/lifecycle execution or permission claim.',
        'proof_status':'unverified','execution_permission':{'allowed':False}}
