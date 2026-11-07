"""Resolve actual owned immutable computations; client references are not evidence."""
from ..core import digest
from ..errors import AssuranceError
from ..symbolic.state import require
from ..symbolic.service import SymbolicService
from ..white_star.service import WhiteStar
from ..white_star import blobs
from ..formal_bridge.fol import check_link


def traces(root, project, source, refs, ceiling):
    checked=[]
    for spec in refs:
        try:
            svc=SymbolicService(root,None) if spec['engine']=='symbolic_v1' else WhiteStar(root,None)
            w,run=svc.load(project,spec['run_id'])
            require(run['status']=='COMPLETED','UNBACKED_ORIGIN')
            require(run['source_sha256']==source['sha256'],'SOURCE_BINDING_MISMATCH')
            inp=w.get(run['input_ref']);result=blobs.get(w,run['result_ref'])
            require(digest(result)==run['result_digest'],'REJECTED_PROVENANCE')
            if spec.get('input_sha256'):require(digest(inp)==spec['input_sha256'],'REJECTED_PROVENANCE')
            raw_source=inp['source'] if spec['engine']=='symbolic_v1' else inp['encoding']['source']
            require(raw_source['sha256']==source['sha256'] and raw_source['text']==source['text_utf8'],'SOURCE_BINDING_MISMATCH')
            if spec['engine']=='symbolic_v1':
                if spec.get('snapshot_sha256'):require(spec['snapshot_sha256']==digest(inp),'REJECTED_PROVENANCE')
                require(inp['normalization']=='none','SOURCE_BINDING_MISMATCH')
                states={s['node_id']:s for s in result['states']};history={h['node_id']:h for h in result['history']}
                ids=spec.get('node_refs') or [h['node_id'] for h in result['history'] if h['op']=='REVERSE'][:ceiling]
                require(bool(ids) and not spec.get('frame_ids'),'UNBACKED_ORIGIN')
                for ident in ids:
                    require(ident in states and ident in history,'UNBACKED_ORIGIN')
                    h=history[ident];state=states[ident]
                    require(all(p in states and p in history for p in h['parent_ids']),'REJECTED_PROVENANCE')
                    if spec.get('parent_ids') is not None:require(spec['parent_ids']==h['parent_ids'],'REJECTED_PROVENANCE')
                    order=[]
                    for token_links in state['source_spans']:
                        for sha,a,b in token_links:
                            require(sha==source['sha256'],'SOURCE_BINDING_MISMATCH')
                            link={'byte_utf8':[a,b],'literal':source['text_utf8'].encode()[a:b].decode()};check_link(source,link)
                            if link not in order:order.append(link)
                    checked.append({'engine':spec['engine'],'run_id':run['run_id'],'result_sha256':run['result_digest'],'input_sha256':digest(inp),'node_ref':ident,'operator':h['op'],'parent_ids':h['parent_ids'],'operator_trace':h,'source_order':order,'snapshot_sha256':digest(inp),'origin_status':'TRACE_LINK_CHECKED'})
            else:
                snapshot=w.get(run['common_snapshot_ref'])
                require(digest(snapshot)==run['common_snapshot_sha256']==result['common_snapshot_sha256'],'REJECTED_PROVENANCE')
                if spec.get('snapshot_sha256'):require(spec['snapshot_sha256']==digest(snapshot),'REJECTED_PROVENANCE')
                frames={f['id']:f for f in result['selected_frames']};concepts={c['id']:c for c in inp['encoding']['concepts']}
                ids=spec.get('frame_ids') or list(frames)[:ceiling]
                require(bool(ids) and not spec.get('node_refs'),'UNBACKED_ORIGIN')
                for ident in ids:
                    require(ident in frames,'UNBACKED_ORIGIN');frame=frames[ident];order=[]
                    for link in frame['links']:
                        for alternative in link['alternatives']:
                            for cid in alternative['alias']['concepts']:
                                require(cid in concepts,'REJECTED_PROVENANCE')
                                for e in concepts[cid]['evidence']:
                                    span={'byte_utf8':[e['byte_start'],e['byte_end']],'literal':e['quote']};check_link(source,span)
                                    if span not in order:order.append(span)
                    checked.append({'engine':spec['engine'],'run_id':run['run_id'],'result_sha256':run['result_digest'],'input_sha256':digest(inp),'frame_id':ident,'operator':'FRAME_CONCEPT_ORDER','operator_trace':frame,'source_order':order,'snapshot_sha256':digest(snapshot),'encoding_assumptions':inp['encoding'],'origin_status':'TRACE_LINK_CHECKED'})
        except AssuranceError as e:
            if e.code in ('SOURCE_BINDING_MISMATCH','REJECTED_PROVENANCE','UNBACKED_ORIGIN'):raise
            raise AssuranceError('UNBACKED_ORIGIN',details={'underlying':e.code,'run_id':spec['run_id']}) from None
    require(len(checked)<=ceiling,'FRAME_BOUND')
    for t in checked:t['trace_sha256']=digest(t)
    return checked
