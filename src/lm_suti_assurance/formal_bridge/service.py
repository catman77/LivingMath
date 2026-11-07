"""Project-owned immutable artifacts and append-only jobs on the shared executor."""

import asyncio
import base64
from ..core import digest, canonical
from ..errors import AssuranceError
from ..symbolic.state import require
from ..symbolic_complex.service import ExtensionService
from ..symbolic_complex.app import binding
from ..white_star import blobs
from .ir import limits


class FormalService:
    def __init__(self,root,executor):
        self.ext=ExtensionService(root,executor)
        self.executor=executor
        self.tasks=set()

    def owned(self,w,ref):
        rows=w.history()
        issued={x for row in rows if row['action'].startswith('formal.') for x in row['object_refs']}
        require(ref in issued,'NOT_FOUND','/object_ref')
        value=w.get(ref)
        return blobs.get(w,ref) if value.get('schema')=='levinmas-white-star-blob/1' else value

    def load(self,w,run_ref):
        rows=w.history()
        end=next((r for r in rows if r['action']=='formal.finish' and r['result']['run_ref']==run_ref),None)
        require(end is not None,'NOT_FOUND','/run_ref')
        return w.get(end['result']['record_ref'])

    def candidate(self,w,run_ref,candidate_ref=None):
        run=self.load(w,run_ref);require(run['status']=='COMPLETED','SOURCE_NOT_COMPLETED')
        result=blobs.get(w,run['result_ref'])
        if result.get('kind') in ('grammar','dfa'):
            require(candidate_ref is None,'INVALID_CANDIDATE_REF')
            return {'candidate_id':digest(result['value']),'ast':result['value'],'origin':'IMPORTED_DATA_NOT_INDUCED'}
        candidates=result.get('candidates',result.get('model',{}).get('candidates',[]))
        selected=candidate_ref or result.get('model',{}).get('selected')
        match=[c for c in candidates if selected in (c['candidate_id'],run['object_index'].get(c['candidate_id']),run['object_index'].get(digest(c)))]
        require(len(match)==1,'NOT_FOUND','/candidate_ref');return match[0]

    def resolve(self,w,operation,p):
        q=dict(p);q['budget']=limits(q.get('budget'))
        if operation=='synthesize':
            q['train']=self.ext.records(w,q.pop('train_ref'),'train');q['queries']=self.ext.records(w,q.pop('predict_ref'),'queries')
        elif operation=='interpret':
            q['source']=self.owned(w,q['source_ref'])
            for ref in q['source']['context_refs']:self.owned(w,ref)
        elif operation=='verify':
            q['candidate']=self.candidate(w,q.pop('run_ref'),q.pop('candidate_ref',None));q['record']=self.owned(w,q.pop('source_ref'))
            if 'proof_ref' in q:q['proof']=self.owned(w,q.pop('proof_ref'))
        elif operation=='contrast':
            run=q.pop('run_ref');refs=q.pop('candidate_refs');q['candidates']=[]
            anchor=self.load(w,run);require(anchor['status']=='COMPLETED','SOURCE_NOT_COMPLETED')
            for ref in refs:
                try:c=self.candidate(w,run,ref)
                except AssuranceError as exc:
                    if exc.code!='NOT_FOUND' and exc.code!='INVALID_CANDIDATE_REF':raise
                    ast=self.owned(w,ref);require(ast.get('schema') in ('formal-grammar-ir/1','formal-dfa-ir/1'),'CANDIDATE_KIND_MISMATCH')
                    c={'candidate_id':digest(ast),'ast':ast,'origin':'IMPORTED_DATA_NOT_INDUCED'}
                q['candidates'].append(c)
        elif operation=='model_check':
            q['candidate']=self.candidate(w,q.pop('run_ref'),q.pop('candidate_ref'));q['model']=self.owned(w,q.pop('model_ref'))
        elif operation=='replay':
            run_ref=q.pop('run_ref');run=self.load(w,run_ref)
            require(run['status']=='COMPLETED' and run['operation']!='replay','INVALID_REPLAY_SOURCE')
            require(run['kernel_binding']==binding(),'KERNEL_BINDING_UNAVAILABLE')
            q.update(original=blobs.get(w,run['packet_ref']),expected_sha256=run['result_sha256'],original_run_ref=run_ref)
        return q

    def reserve(self,project,key,operation,payload):
        w=self.ext.workspace(project);namespaced='formal.start:'+digest([operation,key]);fresh=[]
        # Immutable replay of an existing key precedes resolver changes.
        with w.locked():
            row=next((r for r in w.history() if r['request_key']==namespaced),None)
            if row:
                require(row['payload_digest']==digest({'action':'formal.start','payload':{'operation':operation,'payload':payload}}),'REQUEST_KEY_CONFLICT')
                return w,w.get(row['result']['start_ref']),False
        def commit(rows):
            resolved=self.resolve(w,operation,payload)
            packet={'action':'observer_verify','formal_packet':{'operation':operation,'payload':resolved}}
            ref,refs=blobs.put(w,packet)
            run_id=digest({'project':project,'key':key,'operation':operation,'packet_sha256':digest(packet),'binding':binding()})
            start={'schema':'formal-run/1','run_ref':run_id,'operation':operation,'status':'RUNNING','packet_ref':ref,'packet_sha256':digest(packet),'kernel_binding':binding(),'execution_permission':False}
            sr=w.put(start);fresh.append(True);return {'run_ref':run_id,'start_ref':sr},[sr,*refs]
        value=w.transact('formal.start',namespaced,{'operation':operation,'payload':payload},commit)
        return w,w.get(value['start_ref']),bool(fresh)

    def finish(self,w,start,data=None,error=None,metrics=None):
        def commit(rows):
            refs=[];index={}
            def put(value,ident=None):
                ref,more=blobs.put(w,value);refs.extend(more);index[ident or digest(value)]=ref;return ref
            record={**start,'status':'COMPLETED' if error is None else 'FAILED','error':error,'metrics':metrics or {},'object_index':index}
            if data is not None:
                packet=blobs.get(w,start['packet_ref'])['formal_packet']['payload']
                for r in packet.get('train',[])+packet.get('queries',[]):put(r)
                if 'record' in packet:put(packet['record'])
                if 'value' in data:record['stored_object_ref']=put(data['value'])
                candidates=data.get('candidates',data.get('model',{}).get('candidates',[]))
                for c in candidates:put(c,c['candidate_id'])
                for pred in data.get('predictions',[]):
                    if 'proof' in pred:put(pred['proof'])
                if 'proof' in data:record['proof_ref']=put(data['proof'])
                record.update(result_ref=put(data),result_sha256=digest(data),result_status=data.get('status'))
            rr=w.put(record);refs.append(rr)
            return {'run_ref':start['run_ref'],'record_ref':rr,'status':record['status']},refs
        return w.transact('formal.finish','formal.finish:'+start['run_ref'],{'run_ref':start['run_ref']},commit)

    async def operation(self,project,request_key,operation,payload):
        w,start,fresh=await asyncio.to_thread(self.reserve,project,request_key,operation,payload)
        if fresh:
            task=asyncio.create_task(self.compute(w,start));self.tasks.add(task);task.add_done_callback(self.tasks.discard);await asyncio.shield(task)
        with w.locked():
            try:return self.summary(self.load(w,start['run_ref']))
            except AssuranceError as exc:
                if exc.code!='NOT_FOUND':raise
                return {'run_ref':start['run_ref'],'status':'RUNNING','execution_permission':False}

    async def compute(self,w,start):
        try:
            reply=await asyncio.to_thread(self.executor.run,blobs.get(w,start['packet_ref']))
            await asyncio.to_thread(self.finish,w,start,reply['data'],None,reply.get('metrics'))
        except AssuranceError as exc:await asyncio.to_thread(self.finish,w,start,None,{'code':exc.code,'details':exc.details})
        except Exception as exc:await asyncio.to_thread(self.finish,w,start,None,{'code':'FORMAL_INTERNAL_ERROR','message':str(exc)[:256]})

    def summary(self,r):
        return {k:v for k,v in r.items() if k not in ('object_index',)}

    def inspect(self,project,run_ref,view='summary',object_ref=None,offset=0,limit=32):
        w=self.ext.workspace(project)
        with w.locked():
            run=self.load(w,run_ref)
            if view=='summary':return self.summary(run)
            require(run['status']=='COMPLETED','SOURCE_NOT_COMPLETED')
            result=blobs.get(w,run['result_ref'])
            if view=='objects':value=[{'identity':k,'object_ref':v} for k,v in sorted(run['object_index'].items())]
            elif view=='object':
                require(object_ref in set(run['object_index'].values())|{run['result_ref'],run['packet_ref']},'NOT_FOUND');value=self.owned(w,object_ref)
            elif view=='packet':value=blobs.get(w,run['packet_ref'])
            elif view=='bundle':value={'schema':'formal-replay-bundle/1','kernel_binding':run['kernel_binding'],'packet':blobs.get(w,run['packet_ref']),'result':result,'result_sha256':run['result_sha256']}
            elif view=='result':value=result
            elif view in ('model','candidates','predictions','considered'):
                value=result.get(view,result.get('model',{}).get(view))
                require(value is not None,'NOT_FOUND')
            else:raise AssuranceError('INVALID_INPUT')
            raw=canonical(value).encode()
            if isinstance(value,list):return {'items':value[offset:offset+limit],'total':len(value),'next_offset':offset+limit if offset+limit<len(value) else None}
            # Large object/packet/result is explicit byte-paginated, never truncated.
            if len(raw)>60000 or offset:
                size=min(limit*1024,49152);chunk=raw[offset:offset+size]
                return {'encoding':'base64','data':base64.b64encode(chunk).decode(),'bytes':len(raw),'sha256':digest(value),'offset':offset,'next_offset':offset+len(chunk) if offset+len(chunk)<len(raw) else None}
            return value

    def recover(self):
        for directory in self.ext.base.root.iterdir():
            if not directory.is_dir() or not (directory/'journal.jsonl').exists():continue
            w=self.ext.workspace(directory.name)
            with w.locked():
                rows=w.history();done={r['result']['run_ref'] for r in rows if r['action']=='formal.finish'};pending=[w.get(r['result']['start_ref']) for r in rows if r['action']=='formal.start' and r['result']['run_ref'] not in done]
            for start in pending:self.finish(w,start,None,{'code':'INTERRUPTED_REAUDIT_REQUIRES_NEW_KEY'})
