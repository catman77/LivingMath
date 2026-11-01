"""Actual archival source bridge and streaming address/provenance validation."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from real_xi015_stream import records


def load_native(directory):
    directory=Path(directory);sys.path.insert(0,str(directory/'vendor'))
    spec=importlib.util.spec_from_file_location('xi015_archival_reproducer',directory/'reproduce.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    if module.sha(directory/'vendor/source.py')!=module.SOURCE_SHA or module.sha(directory/'vendor/intervals.py')!=module.INTERVAL_SHA:
        raise ValueError('ORIGINAL_SOURCE_HASH_MISMATCH')
    return module


def address(row):
    a=row['source_address'];return (a['cell'],a['node'],a['n'],a['branch'],row['origin_id'])


def audit_export(path):
    catalog={};origins={};selected={};case_meta={};orders={};row_hashes={};counts={};header={}
    for kind,key,value in records(path):
        if kind=='source_nodes' and key<4:catalog[key]=value
        elif kind=='origins' and key<16:origins[key]=value
        elif kind=='meta':header[key]=value
        elif kind=='case_meta':case_meta.setdefault(key,{})[value[0]]=value[1]
        elif kind=='edge':
            index=counts.get(key,0);counts[key]=index+1
            if value['index']!=index:raise ValueError('EDGE_ORDER_NOT_CONTIGUOUS')
            identity=address(value)
            expected_origin=(identity[0]*8+identity[1])*4+identity[2]-1
            if expected_origin!=value['origin_id'] or index!=2*expected_origin+(identity[3]=='-'):
                raise ValueError('SOURCE_ADDRESS_ORIGIN_MISMATCH')
            orders.setdefault(key,[]).append(identity)
            row_hashes.setdefault(key,hashlib.sha256()).update(json.dumps(value,sort_keys=True,separators=(',',':')).encode())
            if index<32 or (key==2 and 912<=index<=919):selected.setdefault(key,{})[index]=value
    if counts!={0:16384,1:16384,2:16384}:raise ValueError('SOURCE_EDGE_COUNT')
    if orders[0]!=orders[1] or orders[0]!=orders[2]:raise ValueError('CASE_ADDRESS_JOIN_NOT_IDENTICAL')
    return {'header':header,'nodes':catalog,'origins':origins,'selected':selected,'case_meta':case_meta,
            'join':{'counts':counts,'address_origin_order_identical':True,'unique_addresses':len(set(orders[0])),
                    'ordered_address_sha256':hashlib.sha256(json.dumps(orders[0],separators=(',',':')).encode()).hexdigest(),
                    'case_row_sha256':{str(k):v.hexdigest() for k,v in row_hashes.items()},
                    'weights':'one immutable shared source_nodes/origins catalog, matched by exact origin_id',
                    'streaming':'one row decoded at a time; retained only32 input rows and8 CASE-C control rows per case'}}


def native_block(module,nodes,origins,h,t):
    # This prefix preserves enumerate(origin) exactly; a non-prefix slice would not.
    node_ids=sorted(map(int,nodes));origin_ids=sorted(map(int,origins))
    if node_ids!=list(range(len(node_ids))) or origin_ids!=list(range(len(origin_ids))):raise ValueError('NONPREFIX_NATIVE_ADDRESS_SLICE')
    I=module.I;params=[(I(*nodes[str(i)]['u']),I(*nodes[str(i)]['quadrature_weight'])) for i in node_ids]
    atoms=[(origins[str(i)]['node_id'],origins[str(i)]['n'],params[origins[str(i)]['node_id']][0],I(*origins[str(i)]['amplitude'])) for i in origin_ids]
    _,rows=module.evaluate(params,atoms,h,I(t))
    for row in rows:
        identity=address(row)
        if row['index']!=2*row['origin_id']+(identity[3]=='-'):raise ValueError('NATIVE_SLICE_REINDEXED')
    return rows
