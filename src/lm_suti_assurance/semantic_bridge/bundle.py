"""Additive wire format using the existing journal/object store and replay engine."""
import io
import zipfile
from pathlib import Path
from .. import core
from ..core import canonical,digest,byte_digest
from ..errors import AssuranceError
from ..policy import can_publish,export_guard
from ..validation import parse,inspect
from ..workspace import validate_history
from ..service import require
from .report import dossier
from .records import validate
from .replay import verify_graph

ROOT=Path(__file__).parent


def application_files():
    return {str(p.relative_to(ROOT)):p.read_bytes() for p in sorted(ROOT.rglob('*'))
            if p.is_file() and p.suffix in ('.py','.json') and '__pycache__' not in p.parts}


def application_digest():return digest({n:byte_digest(v) for n,v in application_files().items()})


def export_rows(workspace,rows,audience,include_source_bytes=True):
    require(audience in ('private','reviewers','public'),'INVALID_AUDIENCE')
    refs={ref for r in rows for ref in r['object_refs']};denied=not include_source_bytes
    for row in rows:
        if row['action']=='source.add':
            a=workspace.get(row['result']['source_ref'])
            denied |=not can_publish(a['snapshot'],a['publication_policy'],audience)
    # Prompts, anchors and derived quote envelopes also carry source bytes.
    # A dependency-only export withholds all project objects rather than leak a derivative.
    excluded=sorted(refs) if denied else []
    files={'journal.jsonl':b''.join((canonical(row)+'\n').encode() for row in rows)}
    if not denied:
        files.update({'objects/'+ref+'.json':canonical(workspace.get(ref)).encode() for ref in sorted(refs)})
        research_dossier=dossier(workspace,rows)
        inspect(research_dossier)
        files['dossier.json']=canonical(research_dossier).encode()
    for path in core.LOCK['source_file_sha256']:files['core/'+path]=(core.ROOT/path).read_bytes()
    for path,raw in application_files().items():files['application/'+path]=raw
    for name,raw in files.items():
        if not name.startswith(('core/','application/')):export_guard(raw.decode())
    manifest={'schema':'lm-suti.semantic.package/1','schema_version':1,'project':workspace.project,
              'audience':audience,**core.identity(),'application_digest':application_digest(),
              'files':{n:byte_digest(v) for n,v in sorted(files.items())},'journal_head':rows[-1]['hash'],
              'source_dependencies':excluded,'include_source_bytes':not denied,'R3':'PENDING','execution_permission':False}
    validate('package',manifest)
    files['package_manifest.json']=canonical(manifest).encode()
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for name,raw in sorted(files.items()):
            info=zipfile.ZipInfo(name,(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100600<<16
            z.writestr(info,raw)
    from ..bundle import MAX_BUNDLE
    require(len(out.getvalue())<=MAX_BUNDLE,'BUNDLE_SIZE_LIMIT')
    return out.getvalue(),manifest


def export(workspace,audience='private',include_source_bytes=True):
    with workspace.locked():
        rows=workspace.history();require(bool(rows),'PROJECT_NOT_FOUND')
        return export_rows(workspace,rows,audience,include_source_bytes)


def replay_files(files,manifest,engine):
    from ..bundle import MemoryWorkspace,replay_rows
    validate('package',manifest)
    expected={'schema','schema_version','project','audience','verifier_digest','binder_digest','application_digest',
              'files','journal_head','source_dependencies','include_source_bytes','R3','execution_permission'}
    require(set(manifest)==expected and manifest['schema_version']==1 and manifest['execution_permission'] is False and
            manifest['R3']=='PENDING','SEMANTIC_MANIFEST_INVALID')
    require(set(files)==set(manifest['files']),'MANIFEST_FILE_SET_MISMATCH')
    require(all(byte_digest(raw)==manifest['files'][name] for name,raw in files.items()),'MANIFEST_SHA_MISMATCH')
    require(manifest['application_digest']==application_digest(),'MIGRATION_REQUIRED')
    require(all(manifest[k]==v for k,v in core.identity().items()),'FROZEN_CORE_INTEGRITY_FAILURE')
    expected_core={'core/'+p for p in core.LOCK['source_file_sha256']}
    expected_app={'application/'+p for p in application_files()}
    require({p for p in files if p.startswith('core/')}==expected_core,'CORE_FILE_SET_MISMATCH')
    require({p for p in files if p.startswith('application/')}==expected_app,'APPLICATION_FILE_SET_MISMATCH')
    for path,sha in core.LOCK['source_file_sha256'].items():require(byte_digest(files['core/'+path])==sha,'FROZEN_CORE_INTEGRITY_FAILURE')
    for path,raw in application_files().items():require(files['application/'+path]==raw,'MIGRATION_REQUIRED')
    rows=[parse(line) for line in files['journal.jsonl'].decode().splitlines()]
    require(validate_history(rows)==manifest['journal_head'],'JOURNAL_HEAD_MISMATCH')
    require(not manifest['source_dependencies'] and manifest['include_source_bytes'] is True,'MISSING_SOURCE_DEPENDENCY')
    objects={}
    for name,raw in files.items():
        if name.startswith('objects/'):
            ref=name.removeprefix('objects/').removesuffix('.json')
            require(len(ref)==64 and byte_digest(raw)==ref,'OBJECT_DIGEST_MISMATCH');objects[ref]=parse(raw.decode())
        else:require(name in {'dossier.json','journal.jsonl'}|expected_core|expected_app,'UNKNOWN_BUNDLE_MEMBER')
    require(set(objects)=={ref for row in rows for ref in row['object_refs']},'OBJECT_SET_MISMATCH')
    verify_graph(objects)
    core_results=replay_rows(rows,objects,manifest['project'],engine,semantic=True,audience=manifest['audience'])
    w=MemoryWorkspace(objects);w.project=manifest['project']
    actual=dossier(w,rows);require(canonical(actual)==canonical(parse(files['dossier.json'].decode())),'DOSSIER_REPLAY_MISMATCH')
    semantic_records=[{'seq':row['seq'],'action':row['action'],'result':row['result']} for row in rows if row['action'].startswith('semantic.')]
    return {'status':'PASS','engine':engine,'project':manifest['project'],**core.identity(),
            'application_digest':application_digest(),'logical_digest':digest({'core':core_results,'semantic':semantic_records}),
            'checks':core_results,'semantic_records':len(semantic_records),'frames':len(actual['frames']),
            'revisions':len(actual['revision_edges']),'journal_head':manifest['journal_head'],'network':'DISABLED',
            'model':'NOT_USED','OAuth':'NOT_USED','R3':'PENDING','execution_permission':False}
