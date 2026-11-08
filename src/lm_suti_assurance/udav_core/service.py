"""Shared immutable Workspace and append-only, project-owned bounded runs."""
import asyncio,base64,time,hashlib
from pathlib import Path
from ..core import canonical,digest
from ..service import Service
from ..symbolic.state import require
from ..white_star import blobs
from .contracts import validate,NUMERIC_POLICY
from .symbolic import binding


class UDAVService:
    def __init__(self,root,executor=None):
        self.base=Service(Path(root));self.executor=executor;self.active=set()

    def load(self,project,run_id):
        w=self.base.workspace(project)
        with w.locked():
            rows=w.history();a=next((r for r in rows if r['action']=='udav.start' and r['result']['run_id']==run_id),None)
            require(a is not None,'NOT_FOUND');b=next((r for r in rows if r['action']=='udav.finish' and r['result']['run_id']==run_id),None)
            return w,w.get(b['result']['record_ref'] if b else a['result']['start_ref'])

    async def explore(self,project,key,engine,request):
        if engine=='symbolic':validate(request)
        else:
            from ..white_star.contracts import preflight
            preflight(request)
        source=request['source'] if engine=='symbolic' else request['encoding']['source']
        require(hashlib.sha256(source['text'].encode()).hexdigest()==source['sha256'],'SOURCE_BINDING_MISMATCH')
        w=self.base.workspace(project);fresh=[];payload={'engine':engine,'request':request,'binding':binding(engine)}
        def start(rows):
            run=digest([project,key,payload]);r=w.put(request);source=request['source'] if engine=='symbolic' else request['encoding']['source']
            value={'schema':'udav-core-run/1','engine':engine,'project':project,'run_id':run,'status':'RUNNING','input_ref':r,'input_sha256':digest(request),'source_sha256':source['sha256'],'kernel_binding':binding(engine),'execution_permission':False};ref=w.put(value);fresh.append(True)
            return {'run_id':run,'start_ref':ref},[r,ref]
        row=await asyncio.to_thread(w.transact,'udav.start','udav-request:'+digest(key),payload,start)
        if fresh:
            task=asyncio.create_task(self.compute(w,w.get(row['start_ref'])));self.active.add(task);task.add_done_callback(self.active.discard);await asyncio.shield(task)
        return (await asyncio.to_thread(self.load,project,row['run_id']))[1]

    async def compute(self,w,start):
        began=time.perf_counter()
        try:
            require(self.executor is not None,'ENGINE_UNAVAILABLE')
            reply=await asyncio.to_thread(self.executor.run,{'action':'explore','engine':start['engine'],'request':w.get(start['input_ref'])})
            self.finish(w,start,reply['data'],metrics={**reply.get('metrics',{}),'worker_wall_s':reply.get('worker_wall_s'),'server_elapsed_s':time.perf_counter()-began})
        except Exception as e:
            from ..errors import AssuranceError
            self.finish(w,start,error={'code':e.code if isinstance(e,AssuranceError) else 'UDAV_JOB_FAILED','message':str(e)[:256]})

    def finish(self,w,start,data=None,error=None,metrics=None):
        def save(rows):
            ref,refs=blobs.put(w,data) if data is not None else (None,[])
            record={**start,'status':'COMPLETED' if error is None else 'FAILED','result_ref':ref,'result_digest':digest(data) if data is not None else None,'error':error,'metrics':metrics or {}}
            rr=w.put(record);return {'run_id':start['run_id'],'record_ref':rr},[rr,*refs]
        return w.transact('udav.finish','udav-finish:'+start['run_id'],{'run_id':start['run_id']},save)

    def inspect(self,project,run_id,view='summary',offset=0,limit=48,expected_result_sha256=None):
        require(view in ('summary','result','diagnostics','bundle') and type(offset) is int and 0<=offset<=64*1024*1024 and type(limit) is int and 1<=limit<=48,'INVALID_INPUT')
        w,r=self.load(project,run_id)
        if expected_result_sha256:require(expected_result_sha256==r.get('result_digest'),'REJECTED_PROVENANCE')
        if view=='summary':return r
        require(r['status']=='COMPLETED','RUN_NOT_COMPLETED');v=blobs.get(w,r['result_ref']);require(digest(v)==r['result_digest'],'REJECTED_PROVENANCE')
        if view=='bundle':v={'schema':'udav-data-only-bundle/1','engine':r['engine'],'project':project,'run_id':run_id,'request':w.get(r['input_ref']),'request_sha256':r['input_sha256'],'result':v,'result_sha256':r['result_digest'],'kernel_binding':r['kernel_binding'],'execution_permission':False}
        elif view=='diagnostics':v=v.get('search_diagnostics',v.get('selection_audit',{}))
        raw=canonical(v).encode();chunk=raw[offset:offset+min(limit*1024,49152)]
        return {'encoding':'base64','data':base64.b64encode(chunk).decode(),'bytes':len(raw),'sha256':digest(v),'offset':offset,'next_offset':offset+len(chunk) if offset+len(chunk)<len(raw) else None,'execution_permission':False}

    async def replay(self,project,run_id,expected_result_sha256=None):
        w,r=await asyncio.to_thread(self.load,project,run_id);require(r['status']=='COMPLETED','RUN_NOT_COMPLETED');require(r['kernel_binding']==binding(r['engine']),'KERNEL_BINDING_UNAVAILABLE')
        v=blobs.get(w,r['result_ref']);require(digest(v)==r['result_digest'],'REJECTED_PROVENANCE')
        if expected_result_sha256:require(expected_result_sha256==r['result_digest'],'REJECTED_PROVENANCE')
        request=w.get(r['input_ref']);require(digest(request)==r['input_sha256'],'REJECTED_PROVENANCE')
        reply=await asyncio.to_thread(self.executor.run,{'action':'explore','engine':r['engine'],'request':request});require(digest(reply['data'])==r['result_digest'],'REPLAY_MISMATCH')
        return {'status':'REPLAY_MATCH','run_id':run_id,'result_sha256':r['result_digest'],'model_calls':0,'network_calls':0,'execution_permission':False}

    def recover(self):
        for d in self.base.root.iterdir():
            if not d.is_dir() or not (d/'journal.jsonl').exists():continue
            w=self.base.workspace(d.name);rows=w.history();done={r['result']['run_id'] for r in rows if r['action']=='udav.finish'}
            for r in rows:
                if r['action']=='udav.start' and r['result']['run_id'] not in done:self.finish(w,w.get(r['result']['start_ref']),error={'code':'INTERRUPTED','message':'Restart before immutable result; use a new key'})
