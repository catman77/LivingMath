"""Offline exported-page audit using the independently supplied checker, no planner."""
import importlib.util
from math import gcd, isqrt
from pathlib import Path


def verify_export(request, records, charts, checker_path):
    spec = importlib.util.spec_from_file_location('supplied_independent_coverage_checker', Path(checker_path))
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    expected_charts, omitted = checker.expected_atlas(request)
    checker.need(charts == expected_charts, 'EXPORTED_ATLAS_MISMATCH')
    expected, cells = checker.partition_targets(expected_charts)
    seen, keys = set(), set()
    for i, r in enumerate(records):
        checker.need(r['obligation'] == i and r['work_unit_key'] not in keys, 'EXPORT_PREFIX_OR_DUPLICATE')
        keys.add(r['work_unit_key'])
        checker.need(r['source_sha256'] == request['encoding']['source']['sha256'], 'SOURCE_BINDING')
        checker.need(type(r['view']) is int and 0 <= r['view'] < len(charts), 'VIEW')
        c = charts[r['view']]
        checker.need(r['matrix'] == c['matrix'] and r['aliases'] == c['aliases'], 'MATRIX_ALIASES')
        checker.need(type(r['alias_index']) is int and 0 <= r['alias_index'] < len(c['aliases']), 'ALIAS')
        u, v = r['witness']
        checker.need(type(u) is int and type(v) is int and min(u,v) >= 0 and u+v > 0, 'WITNESS')
        a,b,c0,d = c['matrix']; x,y = a*u+b*v,c0*u+d*v
        checker.need(all(type(z) is int for z in r['coordinates']), 'NONINTEGER_COORDINATES')
        checker.need([x,y] == r['coordinates'], 'PROJECTION')
        checker.need(r['target'] == checker.reading(c['aliases'][r['alias_index']]['concepts'],x,y), 'TARGET')
        t=r['orbit_index']; s=(isqrt(8*t+1)-1)//2; pos=t-s*(s+1)//2
        seed=request['encoding']['protocol']['seed']; stride=2*(seed%19)+1
        while gcd(stride,s+1)!=1: stride+=2
        aa=(pos*stride+seed)%(s+1)
        checker.need([aa,s-aa] == [u,v], 'ORBIT')
        checker.need(r['prefix_was_executed'] is False and r['witness_origin']=='CONSTRUCTED_CERTIFIED_WITNESS', 'ORIGIN')
        checker.need(r['integer_projection_checked'] is True and r['primitive']=='SUPPLIED_cad.project', 'PRIMITIVE')
        checker.need(r['execution_permission'] is False and r['source_truth']=='NOT_VERIFIED', 'FALSE_CLAIM')
        checker.need(r['receipt_sha256']==checker.sha({k:v for k,v in r.items() if k!='receipt_sha256'}), 'RECEIPT_HASH')
        seen.add(checker.enc(r['target']))
    checker.need(len(seen)==len(records) and seen==expected, 'INCOMPLETE_OR_EXTRANEOUS_EXPORT')
    return {'status':'PASS','targets':len(expected),'exact_partition_cells':cells,'charts':len(charts),
            'omitted_collinear_pairs':len(omitted),'all_receipts_checked':len(records),
            'checker':'SUPPLIED_INDEPENDENT_CHECKER_NO_PRODUCTION_PLANNER_IMPORT','source_semantics':'NOT_VERIFIED'}
