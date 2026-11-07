"""Append-only proposal jobs in the current Workspace; no semantic activation."""
import asyncio,base64,json,time
from pathlib import Path
from ..core import digest,canonical
from ..errors import AssuranceError
from ..formal_bridge.service import FormalService
from ..formal_bridge.fol import signature
from ..symbolic.state import require
from ..white_star import blobs
from .decoder import source_packet,decode,replay_bundle,build_request
from .provenance import traces

class NLService:
    def __init__(self,root,executor,provider=None):
        self.root=Path(root);self.formal=FormalService(root,executor);self.provider=provider;self.tasks=set();self.admission=asyncio.Lock()
    def load(self,w,ref):
        rows=w.history();end=next((r for r in rows if r['action']=='nl.finish' and r['result']['run_ref']==ref),None)
        if end:return w.get(end['result']['record_ref'])
        start=next((r for r in rows if r['action']=='nl.start' and r['result']['run_ref']==ref),None)
        require(start is not None,'NOT_FOUND');return w.get(start['result']['start_ref'])
    def prepare(self,project,args):
        w=self.formal.ext.workspace(project);items=[];mode=args['policy']['mode']
        for item in args.get('items') or [{k:args[k] for k in ('source_ref','target_signature','structural_run_refs','expected_source_sha256') if k in args}]:
            s=self.formal.owned(w,item['source_ref']);signature(item['target_signature']);packet=source_packet(s,args.get('normalization','none'))
            contexts=[{'ref':ref,'record':self.formal.owned(w,ref)} for ref in s['context_refs']]
            if item.get('expected_source_sha256'):require(item['expected_source_sha256']==s['sha256'],'SOURCE_BINDING_MISMATCH')
            refs=item.get('structural_run_refs',[])
            require((not refs) if mode=='source_only' else bool(refs),'TRACE_POLICY_MISMATCH')
            if mode=='white_star_structural':require(all(r['engine']=='symbolic_v1' for r in refs),'TRACE_POLICY_MISMATCH')
            if mode=='white_star_numeric':require(all(r['engine']=='white_star' for r in refs),'TRACE_POLICY_MISMATCH')
            checked=traces(self.root,project,s,refs,args['policy']['max_frames'])
            items.append({'source_ref':item['source_ref'],'packet':packet,'signature':item['target_signature'],'traces':checked,**({'contexts':contexts} if contexts else {})})
        return w,items
    def reserve(self,project,key,args):
        w=self.formal.ext.workspace(project);key='nl.start:'+digest(key);fresh=[]
        with w.locked():
            old=next((r for r in w.history() if r['request_key']==key),None)
            if old:
                require(old['payload_digest']==digest({'action':'nl.start','payload':args}),'REQUEST_KEY_CONFLICT');return w,w.get(old['result']['start_ref']),False
        require(len(self.tasks)<4,'NL_RESOURCE_BUSY')
        _,items=self.prepare(project,args)
        def commit(rows):
            packet={'items':items,'policy':args['policy']};pr,refs=blobs.put(w,packet)
            start={'schema':'nl-proposal-run/1','run_ref':digest([project,key,args]),'status':'RUNNING','packet_ref':pr,'execution_permission':False}
            sr=w.put(start);fresh.append(True);return {'run_ref':start['run_ref'],'start_ref':sr},[sr,*refs]
        result=w.transact('nl.start',key,args,commit);return w,w.get(result['start_ref']),bool(fresh)
    def finish(self,w,start,result=None,error=None):
        def commit(rows):
            extra=[]
            if result is not None:
                for item in result.get('items',[]):
                    ar,more=blobs.put(w,item['analysis']);extra.extend(more);item['source_analysis_ref']=ar
                    for c in item['candidates']:
                        c['source_analysis_ref']=ar
                        c['competing_parse_refs']=[x['candidate_id'] for x in item['candidates'] if x is not c]
            rr,refs=blobs.put(w,result) if result is not None else (None,[])
            refs.extend(extra)
            record={**start,'status':'COMPLETED' if error is None else 'FAILED','result_ref':rr,'result_sha256':digest(result) if result else None,'error':error}
            record_ref=w.put(record);return {'run_ref':start['run_ref'],'record_ref':record_ref},[record_ref,*refs]
        return w.transact('nl.finish','nl.finish:'+start['run_ref'],{'run_ref':start['run_ref']},commit)
    async def propose(self,project,key,args):
        async with self.admission:
            w,start,fresh=await asyncio.to_thread(self.reserve,project,key,args)
            if fresh:
                task=asyncio.create_task(self.compute(w,start));self.tasks.add(task);task.add_done_callback(self.tasks.discard)
            return self.load(w,start['run_ref'])
    async def compute(self,w,start):
        try:
            frozen=blobs.get(w,start['packet_ref']);policy=frozen['policy'];items=frozen['items']
            if self.provider is None:
                self.finish(w,start,{'status':'PROVIDER_UNAVAILABLE','model_calls':0,'candidates':[],'execution_permission':False});return
            request=build_request(items,policy)
            receipt=await self.provider.generate(request)
            if receipt['status']!='OK':self.finish(w,start,{'status':'PROVIDER_UNAVAILABLE','receipt':receipt,'candidates':[],'execution_permission':False});return
            require(receipt.get('request_sha256')==digest(request) and receipt.get('request')==request and receipt.get('tools_used')==0,'PROVIDER_RECEIPT_MISMATCH')
            usage=receipt.get('usage') or {};consumed=usage.get('input_tokens',0)+usage.get('output_tokens',0)
            require(consumed<=policy['max_tokens'],'TOKEN_BUDGET_EXCEEDED')
            from jsonschema import Draft202012Validator
            from .provider import SCHEMA
            answer=json.loads(receipt['raw_output']);Draft202012Validator(SCHEMA).validate(answer)
            require(isinstance(answer,dict) and len(answer['items'])==len(items),'PROVIDER_RESULT_MISMATCH')
            decoded=[];began=time.process_time();bundle_items=[]
            for i,a in zip(items,answer['items']):
                value=decode(i['packet'],i['signature'],a,receipt,i['traces'],policy);decoded.append(value);bundle_items.append({**i,'answer':a})
            cpu_ms=(time.process_time()-began)*1000;require(cpu_ms<=policy['max_cpu_ms'],'CPU_BUDGET_EXCEEDED')
            bundle={'schema':'nl-frozen-bundle/1','policy':policy,'items':bundle_items,'receipt':receipt,'receipt_digest':digest(receipt),'decoded_sha256':digest(decoded)}
            result={'schema':'nl-proposal-result/1','status':'PROPOSED','items':[],'receipt':receipt,'bundle':bundle,'metrics':{'model_calls':1,'tokens':usage,'CPU_ms':cpu_ms,'provider_s':receipt.get('duration_s'),'cost_USD':None},'semantic_adjudication':'EXTERNAL_ADJUDICATION_NOT_EXECUTED','execution_permission':False}
            for index,(i,d) in enumerate(zip(items,decoded)):
                output={'source_ref':i['source_ref'],'source_sha256':i['packet']['source']['sha256'],**d,'formal_run_ref':None,'contrast_ref':None}
                if d['candidates']:
                    proposals=[{'formula_ast':c['formula_ast'],'assumptions':[],'token_role_links':c['token_role_links'],'construction_trace':[{'source_analysis_sha256':digest(d['analysis']),'receipt_digest':digest(receipt),'moves':c['structural_move_log'],'added_assumptions':c['added_assumptions'],'warning':'PROPOSED_ONLY'}]} for c in d['candidates']]
                    f=await self.formal.operation(w.project,'nl:'+start['run_ref']+':'+str(index),'interpret',{'source_ref':i['source_ref'],'target_signature':i['signature'],'candidate_provider':{'kind':'external_llm','provenance':{'receipt_digest':digest(receipt),'bridge':'NLProposalBridge/1','verified_origin_is_not_verified_semantics':True}},'proposals':proposals})
                    require(f['status']=='COMPLETED','FORMAL_CHECK_FAILED');output['formal_run_ref']=f['run_ref']
                    candidates=self.formal.inspect(w.project,f['run_ref'],'candidates')['items']
                    for c,fc in zip(output['candidates'],candidates):
                        require(digest(fc['formula_ast'])==c['candidate_ast_sha'],'REJECTED_PROVENANCE')
                        c.update(candidate_id=fc['candidate_id'],source_ref=i['source_ref'],source_sha256=i['packet']['source']['sha256'],source_spans=c['token_role_links'],source_analysis_ref=digest(d['analysis']),white_star_trace_refs=[t['trace_sha256'] for t in i['traces']] if c['structural_move_log'] else [],premise_ledger=[{'claim':a,'status':'UNADJUDICATED_ASSUMPTION'} for a in c['added_assumptions']],scope={'model_class':'EXPLICIT_CLOSED_FINITE_MODELS','quantifier_domain':i['signature']['sorts'],'context_refs':i['packet']['source']['context_refs']},creator={'provider':'owner_hosted','model_id':receipt.get('model_id'),'seed':None,'requested_search_seed':policy['seed'],'receipt_digest':digest(receipt)},checker_receipt_ref=f['run_ref'],contrast_refs=[])
                    if len(candidates)>1:
                        contrast=await self.formal.operation(w.project,'nl:'+start['run_ref']+':contrast:'+str(index),'contrast',{'run_ref':f['run_ref'],'candidate_refs':[c['candidate_id'] for c in candidates]})
                        output['contrast_ref']=contrast['run_ref']
                        for c in output['candidates']:c['contrast_refs']=[contrast['run_ref']]
                result['items'].append(output)
            # decode() outputs were enriched above; replay hash must bind its pure output before enrichment.
            result['bundle']['decoded_sha256']=digest([decode(i['packet'],i['signature'],i['answer'],receipt,i['traces'],policy) for i in bundle_items])
            self.finish(w,start,result)
        except Exception as exc:
            self.finish(w,start,None,{'code':exc.code if isinstance(exc,AssuranceError) else 'NL_OPERATION_FAILED','message':str(exc)[:256]})
    def inspect(self,project,run_ref,view='summary',expected_ast_sha256=None,offset=0,limit=32):
        w=self.formal.ext.workspace(project)
        with w.locked():
            record=self.load(w,run_ref)
            if view=='summary':return record
            require(record['status']=='COMPLETED','SOURCE_NOT_COMPLETED');result=blobs.get(w,record['result_ref'])
            if expected_ast_sha256:require(any(c['candidate_ast_sha']==expected_ast_sha256 for i in result.get('items',[]) for c in i['candidates']),'REJECTED_PROVENANCE')
            if view=='replay':return replay_bundle(result['bundle'])
            value=result['bundle'] if view=='bundle' else result
            raw=canonical(value).encode()
            if len(raw)>50000 or offset:
                chunk=raw[offset:offset+min(limit*1024,49152)];return {'encoding':'base64','data':base64.b64encode(chunk).decode(),'bytes':len(raw),'sha256':digest(value),'offset':offset,'next_offset':offset+len(chunk) if offset+len(chunk)<len(raw) else None}
            return value
    def recover(self):
        for d in self.root.iterdir():
            if not d.is_dir() or not (d/'journal.jsonl').exists():continue
            w=self.formal.ext.workspace(d.name);rows=w.history();ended={r['result']['run_ref'] for r in rows if r['action']=='nl.finish'}
            for row in rows:
                if row['action']=='nl.start' and row['result']['run_ref'] not in ended:self.finish(w,w.get(row['result']['start_ref']),None,{'code':'INTERRUPTED_REQUIRES_NEW_KEY'})
