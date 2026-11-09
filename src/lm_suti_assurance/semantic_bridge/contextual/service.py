"""Append-only contextual runs on the actual FormalService-owned Workspace."""
import asyncio,base64
from ...core import digest,canonical
from ...errors import AssuranceError
from ...formal_bridge.service import FormalService
from ...formal_bridge import fol
from ...symbolic.state import require
from ...white_star import blobs
from .contracts import source_bindings
from .engine import binding


class ContextualService:
    def __init__(self,root,executor=None):
        self.formal=FormalService(root,executor);self.executor=executor;self.tasks=set()

    def load(self,w,ref):
        rows=w.history();row=next((x for x in rows if x['action']=='semantic_bridge.finish' and x['result']['run_ref']==ref),None)
        if row:return w.get(row['result']['record_ref'])
        row=next((x for x in rows if x['action']=='semantic_bridge.start' and x['result']['run_ref']==ref),None)
        require(row is not None,'NOT_FOUND');return w.get(row['result']['start_ref'])

    def result(self,w,record):
        require(record['status']=='COMPLETED','SOURCE_NOT_COMPLETED');v=blobs.get(w,record['result_ref']);require(digest(v)==record['result_sha256'],'REJECTED_PROVENANCE');return v

    def prepare(self,w,operation,args):
        if operation=='register':
            source=self.formal.owned(w,args['source_ref']);source_bindings(args,source);fol.signature(args['target_signature'])
            contexts=[{'ref':ref,'record':self.formal.owned(w,ref)} for ref in source['context_refs']]
            return {'arguments':args,'source':source,'contexts':contexts}
        record=self.load(w,args['batch_ref']);require(record['operation']=='register','INVALID_BATCH');batch=self.result(w,record)
        budget=args.get('budget',{});require(len(args['pairs'])<=min(budget.get('max_pairs',10),10) and len(args['model_refs'])<=8,'PAIR_OR_SCENARIO_BOUND')
        lookup={}
        for h in batch['hypotheses']:
            for k in [h['client_id'],h['hypothesis_ref']]:lookup[k]=h['hypothesis_ref']
        pairs=[]
        for a,b in args['pairs']:
            require(a in lookup and b in lookup and lookup[a]!=lookup[b],'NOT_FOUND');pairs.append([lookup[a],lookup[b]])
        require(len({tuple(sorted(p)) for p in pairs})==len(pairs),'DUPLICATE_PAIR')
        require(len(set(args['model_refs']))==len(args['model_refs']),'DUPLICATE_MODEL')
        models=[]
        for ref in args['model_refs']:
            model=self.formal.owned(w,ref);fol.check_model(model,batch['target_signature']);models.append({'model_ref':ref,'model':model,'origin':args.get('scenario_origin','LLM_PROPOSED')})
        return {'batch_ref':args['batch_ref'],'batch':batch,'pairs':pairs,'models':models,'budget':budget}

    def reserve(self,project,key,operation,args):
        w=self.formal.ext.workspace(project);request='semantic_bridge.request:'+digest(key);payload={'operation':operation,'arguments':args};fresh=[]
        with w.locked():
            old=next((r for r in w.history() if r['request_key']==request),None)
            if old:
                require(old['payload_digest']==digest({'action':'semantic_bridge.start','payload':payload}),'REQUEST_KEY_CONFLICT');return w,self.load(w,old['result']['run_ref']),False
            resolved=self.prepare(w,operation,args)
        def commit(rows):
            packet={'operation':operation,'payload':resolved};pr,refs=blobs.put(w,packet);run=digest([project,key,operation,args,binding()]);start={'schema':'semantic-bridge-run/1','run_ref':run,'operation':operation,'status':'RUNNING','packet_ref':pr,'packet_sha256':digest(packet),'kernel_binding':binding(),'LLM_calls':0,'execution_permission':False}
            sr=w.put(start);fresh.append(True);return {'run_ref':run,'start_ref':sr},[sr,*refs]
        row=w.transact('semantic_bridge.start',request,payload,commit);return w,self.load(w,row['run_ref']),bool(fresh)

    def finish(self,w,start,data=None,error=None,metrics=None):
        def commit(rows):
            refs=[]
            if data is not None:
                for h in data.get('hypotheses',[]):
                    value={k:v for k,v in h.items() if k!='hypothesis_ref'};ref=w.put(value);require(ref==h['hypothesis_ref'],'HYPOTHESIS_IDENTITY_MISMATCH');refs.append(ref)
                for e in data.get('graph',{}).get('relations',[]):
                    for cm in e.get('countermodels',[]):
                        ref=w.put(cm['model']);require(ref==cm['model_ref'],'MODEL_IDENTITY_MISMATCH');refs.append(ref)
                    proofs=[e.get('alpha',{}),*e.get('directions',{}).values()]
                    for proof in proofs:
                        if 'certificate' in proof:refs.append(w.put(proof['certificate']))
                rr,more=blobs.put(w,data);refs.extend(more)
            else:rr=None
            record={**start,'status':'COMPLETED' if error is None else 'FAILED','result_ref':rr,'result_sha256':digest(data) if data is not None else None,'error':error,'metrics':metrics or {}}
            if data is not None and start['operation']=='register':record.update(batch_ref=start['run_ref'],hypothesis_refs=data['hypothesis_refs'],rejected_or_unsupported=data['rejected_or_unsupported'])
            ref=w.put(record);return {'run_ref':start['run_ref'],'record_ref':ref},[ref,*refs]
        return w.transact('semantic_bridge.finish','semantic_bridge.finish:'+start['run_ref'],{'run_ref':start['run_ref']},commit)

    async def operation(self,project,key,operation,args):
        w,start,fresh=await asyncio.to_thread(self.reserve,project,key,operation,args)
        if fresh:
            task=asyncio.create_task(self.compute(w,start));self.tasks.add(task);task.add_done_callback(self.tasks.discard);await asyncio.shield(task)
        return (await asyncio.to_thread(self.inspect,project,start['run_ref']))

    async def compute(self,w,start):
        try:
            require(self.executor is not None and self.executor.status()['ready'],'UNAVAILABLE')
            packet=blobs.get(w,start['packet_ref']);require(digest(packet)==start['packet_sha256'],'REJECTED_PROVENANCE')
            reply=await asyncio.to_thread(self.executor.run,{'action':'explore','request':packet})
            self.finish(w,start,reply['data'],metrics={**reply.get('metrics',{}),'worker_wall_s':reply.get('worker_wall_s')})
        except Exception as e:self.finish(w,start,error={'code':e.code if isinstance(e,AssuranceError) else 'CONTEXTUAL_JOB_FAILED','message':str(e)[:256]})

    def inspect(self,project,batch_or_run_ref,view='summary',offset=0,limit=32,expected_result_sha256=None):
        w=self.formal.ext.workspace(project)
        with w.locked():
            r=self.load(w,batch_or_run_ref)
            if expected_result_sha256:require(expected_result_sha256==r.get('result_sha256'),'REJECTED_PROVENANCE')
            if view=='summary':return r
            result=self.result(w,r);packet=blobs.get(w,r['packet_ref']);require(digest(packet)==r['packet_sha256'],'REJECTED_PROVENANCE')
            if view=='bundle':value={'schema':'semantic-bridge-replay-bundle/1','operation':r['operation'],'kernel_binding':r['kernel_binding'],'packet':packet,'packet_sha256':r['packet_sha256'],'result':result,'result_sha256':r['result_sha256'],'LLM_calls':0,'execution_permission':False}
            elif view=='graph':value=result.get('graph',{'nodes':result.get('hypotheses',[]),'relations':[],'hypotheses_merged':False})
            elif view=='obligations':value=result.get('obligations',[{'hypothesis_ref':h['hypothesis_ref'],'items':h['obligations']} for h in result.get('hypotheses',[])])
            elif view=='checks':value=result.get('checks',{'typechecks':result.get('rejected_or_unsupported',[]),'LLM_calls':0,'semantic_adjudication':'NOT_EVALUATED','execution_permission':False})
            else:raise AssuranceError('INVALID_INPUT')
            require(type(offset) is int and 0<=offset<=33554432 and type(limit) is int and 1<=limit<=48,'INVALID_INPUT')
            raw=canonical(value).encode();chunk=raw[offset:offset+limit*1024]
            return {'encoding':'base64','data':base64.b64encode(chunk).decode(),'bytes':len(raw),'sha256':digest(value),'offset':offset,'next_offset':offset+len(chunk) if offset+len(chunk)<len(raw) else None,'execution_permission':False}

    async def replay(self,project,run_ref,expected_result_sha256):
        w=self.formal.ext.workspace(project)
        with w.locked():
            r=self.load(w,run_ref);require(r.get('result_sha256')==expected_result_sha256,'REJECTED_PROVENANCE');require(r['kernel_binding']==binding(),'KERNEL_BINDING_UNAVAILABLE');self.result(w,r);packet=blobs.get(w,r['packet_ref']);require(digest(packet)==r['packet_sha256'],'REJECTED_PROVENANCE')
        require(self.executor is not None and self.executor.status()['ready'],'UNAVAILABLE');reply=await asyncio.to_thread(self.executor.run,{'action':'explore','request':packet});require(digest(reply['data'])==r['result_sha256'],'REPLAY_MISMATCH')
        return {'status':'REPLAY_MATCH','run_ref':run_ref,'result_sha256':r['result_sha256'],'kernel_binding':binding(),'LLM_calls':0,'network_calls':0,'execution_permission':False}

    def recover(self):
        for directory in self.formal.ext.base.root.iterdir():
            if not directory.is_dir() or not (directory/'journal.jsonl').exists():continue
            w=self.formal.ext.workspace(directory.name)
            with w.locked():
                rows=w.history();done={x['result']['run_ref'] for x in rows if x['action']=='semantic_bridge.finish'};pending=[w.get(x['result']['start_ref']) for x in rows if x['action']=='semantic_bridge.start' and x['result']['run_ref'] not in done]
            for start in pending:self.finish(w,start,error={'code':'INTERRUPTED_REQUIRES_NEW_KEY'})
