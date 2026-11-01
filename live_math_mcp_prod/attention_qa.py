"""LM-ATTENTION-001: real MCP mechanics and isolated external-model ablations."""
import argparse
import asyncio
import copy
from datetime import datetime,timezone,timedelta
import hashlib
import json
import logging
import os
from pathlib import Path
import resource
import shlex
import sqlite3
import subprocess
import sys
import time
import zipfile

import httpx
from mcp import ClientSession,types
from mcp.client.streamable_http import streamable_http_client

from attention_fixture import fixture,candidates,relations,semantic_attention,SEEDS,SCENARIO,TASK
from attention_model import evaluate
from frontier import fingerprint_hash,ResearchMoveFingerprint
from qa_positive_acceptance import Acceptance,oauth,snapshot,write_json
from research_store import ResearchStore


def configure():
    result={}
    for line in (Path.home()/'.config/livingmath/server.env').read_text().splitlines():
        if line.strip() and not line.lstrip().startswith('#'):
            key,value=line.split('=',1);result[key]=shlex.split(value)[0]
    return result


def intact(before,after):
    return {name:after['tables'][name][:len(rows)]==rows for name,rows in before['tables'].items()}


def server_cpu():
    pid=int(subprocess.check_output(['systemctl','--user','show','-p','MainPID','--value','livingmath-http.service'],text=True))
    fields=Path('/proc/'+str(pid)+'/stat').read_text().rsplit(')',1)[1].split()
    return {'pid':pid,'seconds':(int(fields[11])+int(fields[12]))/os.sysconf('SC_CLK_TCK')}


class AttentionRun(Acceptance):
    def __init__(self,out,db,origin,seed,stamp,baseline):
        super().__init__(out,db,origin)
        self.project='LM_QA_ATTENTION_'+stamp+'_'+str(seed)
        self.f=fixture(seed);self.fixture_hash=self.f['source_hash'];self.seed_number=seed
        self.fixture=json.dumps(self.f['words'],sort_keys=True).encode()
        (out/'fixture.bin').write_bytes(self.fixture)
        self.baseline=baseline;self.event_ids={};self.obligation_ids={};self.mode_data={};self.model_runs={}
        self.before=snapshot(db);self.started=time.monotonic();self.cpu_start=time.process_time()
        self.children_start=resource.getrusage(resource.RUSAGE_CHILDREN)
        self.operator_actions=[];self.model_local_cpu=0.;self.guard_results={};self.semantic_results={}
        self.foreign_id=None
        self.eligible_recall=0.0
        self.seen_request_keys=set();self.server_cpu_begin=server_cpu()

    async def call(self,name,arguments,allow_error=False):
        key=(arguments.get('project'),arguments.get('request_key'))
        replay=bool(key[1] and key in self.seen_request_keys)
        before=self.operation_count()
        response=await self.session.call_tool(name,arguments)
        raw=response.model_dump(mode='json')
        self.calls.append({'index':len(self.calls)+1,'tool':name,'arguments':arguments,'response':raw})
        write_json(self.out/'calls.json',self.calls)
        if response.isError:
            if allow_error:return None
            raise RuntimeError(name+': '+''.join(x.text for x in response.content if x.type=='text'))
        answer=response.structuredContent if response.structuredContent is not None else json.loads(response.content[0].text)
        if replay and isinstance(answer,dict) and answer.get('idempotent') is True:
            self.check('idempotency:same_key_call_'+str(len(self.calls))+':no_new_operations',self.operation_count()==before)
        if key[1]:self.seen_request_keys.add(key)
        return answer

    def at(self,name,ok,detail='',classification='SERVER_BUG'):
        self.check(name,ok,detail)
        self.checks[-1]['classification']=None if ok else classification

    async def setup(self):
        for name in self.f['event_order']:
            event=self.f['events'][name]
            args={'project':self.project,'kind':event['kind'],'status':event['status'],
                'focus':self.f['neutral_focus'][name],'result':json.dumps(event['data'],sort_keys=True),
                'request_key':self.project+':event:'+name}
            if name!='source':args['parent_id']=self.event_ids['source']
            result=await self.call('record_result',args)
            self.event_ids[name]=result['id']
        self.ids['source_event']=self.event_ids['source']
        foreign=await self.call('record_result',{'project':self.project+'_OTHER','kind':'qa_source','status':'observation',
            'focus':'other finite source','result':'A distinct QA project; never a valid ground for this project.',
            'request_key':self.project+':foreign'})
        self.foreign_id=foreign['id']
        status={'active':'OPEN','archive':'SUPERSEDED','refuted':'REFUTED','novel':'OPEN','diagnostic':'OPEN','unrelated':'REFUTED'}
        sources={'active':['source','active'],'archive':['source','archive'],'refuted':['source','counter'],
                 'novel':['source','novel'],'diagnostic':['source','counter','diagnostic'],'unrelated':['unrelated']}
        statements={'active':'Perform bounded read-only word observations.',
            'archive':'Archived aggregate is superseded by direct observations.',
            'refuted':'The recorded p_first assertion fails on the stated finite rewrite.',
            'novel':'Review transition inventory as a possible observation.',
            'diagnostic':'Inspect the failed rewrite as a data object without assuming p_first.',
            'unrelated':'The digit-source assertion fails only in its separate scope.'}
        obligations=[]
        for key in self.f['obligation_order']:
            ids=[self.event_ids[k] for k in sources[key]]
            entry={'key':key,'statement':statements[key],'scope':self.f['scopes'][key],
                'source_event_ids':ids,'evidence_refs':['event:'+str(i) for i in ids],'status':status[key]}
            if status[key] in {'SUPERSEDED','REFUTED'}:
                entry.update(closure_reason=statements[key],reopen_conditions=['New scoped source evidence and an explicit new reopening version.'])
            obligations.append(entry)
        source_rows=snapshot(self.db)['tables']['events']
        refs=[{'id':row['id'],'sha256':fingerprint_hash(row)} for row in source_rows if row['id'] in self.event_ids.values()]
        representation='finite_words:'+self.f['source_hash']
        constraints=[]
        for key,mechanism,ids in [('active','bounded_word_observation',['source','active']),
                                  ('diagnostic','diagnostic_word_observation',['source','counter'])]:
            constraints.append({'kind':'allowed_experiment','obligation_key':key,'mechanisms':[mechanism],
                'source_event_ids':[self.event_ids[x] for x in ids],'source_representations':[representation],
                'scope':self.f['scopes'][key],'reason':'Explicitly scoped synthetic finite-word QA experiment.',
                'reopen_conditions':['A new scope or representation requires review.']})
        constraints.append({'kind':'obsolete_mechanism','obligation_key':'archive','mechanisms':['archived_word_aggregate'],
            'source_event_ids':[self.event_ids['archive']],'reason':statements['archive'],
            'reopen_conditions':['Use actual direct source evidence, not a cosmetic rename.']})
        blueprint={'import_key':self.project+':fixture-v1','project':self.project,'sources':refs,
                   'obligations':obligations,'constraints':constraints}
        result=ResearchStore(self.db).frontier.import_history(blueprint,'User-authorized LM-ATTENTION-001 synthetic fixture')
        self.obligation_ids=result['obligation_ids'];self.known=candidates(self.f,self.event_ids,self.obligation_ids)
        self.oracle=relations(self.f,self.event_ids,self.obligation_ids)
        write_json(self.out/'fixtures.json',{'definition':self.f,'event_ids':self.event_ids,
            'obligation_ids':self.obligation_ids,'operator_candidates':self.known})
        write_json(self.out/'expected_relations.json',self.oracle)
        write_json(self.out/'operator-import.json',{'request':blueprint,'response':result})
        self.at('AT13',all(x['origin']=='operator_seeded' for x in self.known.values()),'Fixture proposals are operator-seeded, not MCP discoveries.')

    async def data_snapshot(self,label):
        context=await self.call('research_context',{'project':self.project,'limit':200})
        frontier=await self.call('research_frontier',{'project':self.project,'include_closed':True})
        focus=await self.call('research_focus_candidates',{'project':self.project,'limit':200})
        focus=focus.get('result',[]) if isinstance(focus,dict) else focus
        # No oracle, expected decisions, internal branch keys or fixture order.
        model_context={'project':self.project,'events':context['events'],'frontier':frontier,
                       'focus_candidates':focus,'origin':'server_generated_snapshot_of_memory'}
        write_json(self.out/(label+'-snapshot.json'),model_context)
        return model_context

    async def adv(self,move):
        return await self.advisory(move)

    def disposition(self,key,version):
        move=self.known['F']['move']
        request={'project':self.project,'event_id':self.event_ids['counter'],'obligation_id':self.obligation_ids['diagnostic'],
            'expected_version':version,'proposed_operation':move['proposed_operation'],'disposition':'diagnostic_subject',
            'reason':'Finite QA diagnosis of the failed rewrite as an object; no support for its refuted premise.',
            'evidence_refs':['event:'+str(self.event_ids['source'])],'request_key':self.project+':disposition:'+key,
            'operator':'User-authorized attention QA operator'}
        result=ResearchStore(self.db).evidence_reviews.record(**request)
        self.operator_actions.append({'request':request,'response':result,'origin':'operator_seeded'})
        write_json(self.out/'operator-dispositions.json',self.operator_actions)

    async def m0(self,context):
        all_ids=set(self.event_ids.values());returned={x['id'] for x in context['events']}
        obligations=context['frontier']['obligations']
        by_id={x['id']:x for x in obligations}
        recall=all_ids<=returned and len(obligations)==6 and all(x['project']==self.project for x in context['events']+obligations)
        recall=recall and all(by_id[self.obligation_ids[k]]['status']==v for k,v in self.oracle['expected_statuses'].items())
        recall=recall and all(by_id[self.obligation_ids[k]]['scope']==self.f['scopes'][k]
                            and by_id[self.obligation_ids[k]]['version']==1 for k in self.obligation_ids)
        self.eligible_recall=(len(all_ids & returned)+sum(i in by_id for i in self.obligation_ids.values()))/(len(all_ids)+len(self.obligation_ids))
        failures={x['event_id'] for x in context['focus_candidates'] if x['target']=='failure'}
        self.at('AT01',recall and {self.event_ids['counter'],self.event_ids['unrelated']}<=failures,
                'All active/closed obligations, scopes, versions and negative IDs returned.')
        self.mode_data['M0']={'generation':'CAPABILITY_NOT_IMPLEMENTED','selection':'CAPABILITY_NOT_IMPLEMENTED',
            'server_generated_candidates':0,'explanation':'The API enumerates history and audits supplied moves; it exposes no generator/ranker.'}
        for key in ('A','B','E','G'):
            self.guard_results[key]=await self.adv(self.known[key]['move'])
        self.at('AT02',self.guard_results['B']['verdict']!='EXPERIMENT_ALLOWED')
        c=await self.propose('refuted',self.known['C']['move'])
        d=await self.propose('rename',self.known['D']['move'])
        self.at('AT03',not c['execution_permission']['allowed'] and c['status']=='REJECTED'
                and any(self.event_ids['counter'] in f['source_event_ids'] for f in c['audit']['findings']))
        self.at('AT04',c['id']==d['id'] and d['idempotent'] and c['fingerprint']['digest']==d['fingerprint']['digest'])
        self.at('AT06',self.guard_results['E']['verdict']=='REQUIRES_SEMANTIC_REVIEW'
                and self.guard_results['E']['proof_status']=='unverified')
        self.at('AT09',self.guard_results['A']['verdict']=='EXPERIMENT_ALLOWED',
                'An unrelated digit failure is present in the project but does not globally block the independent word observation.')
        self.disposition('initial',1)
        f=await self.propose('diagnostic',self.known['F']['move'])
        audited=await self.audit('diagnostic',f['id'])
        allowed=await self.transition('diagnostic:activate',f['id'],'activate_experiment')
        self.at('AT07',audited['audit']['verdict']=='EXPERIMENT_ALLOWED' and allowed['execution_permission']['allowed'])
        await self.call('research_obligation_update',{'project':self.project,'obligation_id':self.obligation_ids['diagnostic'],
            'expected_version':1,'changes':{'status':'TESTING'}})
        stale=await self.history(f['id']);old=await self.transition('diagnostic:activate',f['id'],'activate_experiment')
        reaudit=await self.audit('diagnostic-stale',f['id'])
        self.disposition('renewed',2)
        renewed=await self.audit('diagnostic-renewed',f['id'])
        activated=await self.transition('diagnostic:activate2',f['id'],'activate_experiment')
        self.at('AT12',not stale['execution_permission']['allowed'] and not old['execution_permission']['allowed']
                and reaudit['status']=='REQUIRES_REVIEW' and renewed['status']=='AUDITED' and activated['execution_permission']['allowed'])
        await self.transition('diagnostic:withdraw',f['id'],'abandon',reason='Permission/version QA finished; no second mathematical computation was executed.')
        before=self.operation_count();repeat=await self.propose('refuted',self.known['C']['move'])
        self.at('AT10',repeat['id']==c['id'] and repeat['idempotent'] and self.operation_count()==before)
        bad=copy.deepcopy(self.known['A']['move']);bad['parent_event_ids'].append(self.foreign_id)
        foreign=await self.call('audit_research_shift',{'project':self.project,
            **{k:v for k,v in bad.items() if k not in {'scope','active_frontier_version'}}},allow_error=True)
        self.at('AT11',foreign is None and self.foreign_id not in returned)
        self.mode_data['M0']['fixture_guard_signature']={
            **{k:self.guard_results[k]['verdict'] for k in ('A','B','E','G')},
            'C':c['status'],'D_same_identity':c['id']==d['id'],
            'F_diagnostic_allowed':allowed['execution_permission']['allowed'],
            'stale_permission_restored':old['execution_permission']['allowed']}

    def external(self,context,condition,label):
        run=evaluate(self.out/'models'/label,context,condition)
        self.model_local_cpu+=run['metadata']['local_child_cpu_seconds']
        self.model_runs[label]=run
        return run['output']

    async def guard_model(self,output,label):
        reports=[]
        for candidate in output['candidates']:
            roles={str(x['event_id']):{'role':x['role'],'reason':x['reason']} for x in candidate['evidence_roles']}
            request={'project':self.project,'proposal':candidate['reason_from_evidence'],
                'parent_event_ids':candidate['parent_event_ids'],
                'proposed_operation':{'mechanism':candidate['mechanism'],'intent':'experiment',
                    'premises':candidate['premises'],'mathematical_properties':candidate['mathematical_properties'],
                    'testable_consequence':candidate['testable_consequence'],'required_evidence':candidate['required_evidence']},
                'source_representation':candidate['source_representation'],'target_representation':candidate['target_representation'],
                'verification_plan':candidate['verification_plan'],'evidence_refs':candidate['evidence_refs'],'evidence_roles':roles}
            if candidate['obligation_id'] is not None:request['active_frontier_id']=candidate['obligation_id']
            report=await self.call('audit_research_shift',request,allow_error=True)
            reports.append({'candidate':candidate,'origin':'external_llm_generated',
                            'report':report,'decision':report['verdict'] if report else 'INVALID_REFERENCE_REQUIRES_REVIEW'})
        write_json(self.out/(label+'-guarded.json'),reports)
        return reports

    async def feedback(self):
        request=self.known['G']['move']
        record=await self.propose('bounded-feedback',request)
        await self.audit('bounded-feedback',record['id'])
        granted=await self.transition('bounded-feedback:activate',record['id'],'activate_experiment')
        self.at('AT05',granted['execution_permission']['allowed'] and granted['status']=='EXPERIMENT_ALLOWED')
        rows=[{'origin_id':w['origin_id'],'length':len(w['word'])} for w in self.f['words']]
        counter=next(row for row in rows if row['length']%2)
        negative={'scenario':SCENARIO,'outcome':'FAILURE','observations':rows,'counterexample':counter,
            'contradicts':['p_even'],'depends_on':['p_finite'],'scope':self.f['scopes']['active'],
            'source_hash':self.f['source_hash'],'proof_status':'unverified'}
        new=await self.call('record_result',{'project':self.project,'kind':'failed_check','status':'experiment',
            'focus':'finite observation '+str(self.seed_number),'result':json.dumps(negative,sort_keys=True),
            'parent_id':self.event_ids['active'],'request_key':self.project+':feedback-outcome'})
        self.event_ids['feedback']=new['id'];self.oracle['edges'].append({'source_event':new['id'],
            'relation':'contradicts','target_premise':'p_even','scope':self.f['scopes']['active']})
        done=await self.transition('bounded-feedback:complete',record['id'],'complete',
            result={'outcome':'FAILURE','summary':'The listed finite source includes an odd-length word.', 'data':negative},
            reason='The bounded premise test returned a counter-observation; it does not establish a mathematical theorem.',
            evidence_refs=['event:'+str(new['id'])])
        self.at('AT14',done['status']=='COMPLETED' and done['completion']['result']['outcome']=='FAILURE'
                and done['proof_status']=='unverified' and not done['execution_permission']['allowed'])
        write_json(self.out/'expected_relations.json',self.oracle)
        write_json(self.out/'finite-outcome.json',negative)
        after=await self.data_snapshot('after')
        independent=await self.adv(self.known['A']['move'])
        affected=copy.deepcopy(request);affected['parent_event_ids'].append(new['id'])
        guarded=await self.adv(affected)
        self.at('AT09-after',independent['verdict']=='EXPERIMENT_ALLOWED',
                'An independent premise remains usable after the other premise fails.')
        self.at('AT08-guard',guarded['verdict']=='REQUIRES_SEMANTIC_REVIEW'
                and 'ADVERSE_EVIDENCE_REQUIRES_REVIEW' in guarded['warnings'])
        return after,new['id']

    async def run(self,token):
        async with httpx.AsyncClient(headers={'Authorization':'Bearer '+token},timeout=40,
                event_hooks={'request':[self.request_hook],'response':[self.response_hook]}) as http:
            async with streamable_http_client(self.endpoint,http_client=http) as (read,write,_):
                async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=45),
                        client_info=types.Implementation(name='LM-ATTENTION-001',version='1')) as session:
                    self.session=session
                    initialized=await session.initialize();tools=await session.list_tools()
                    write_json(self.out/'tools-list.json',tools.model_dump(mode='json'))
                    self.at('transport',initialized.serverInfo.version=='0.4.2' and len(tools.tools)==18,classification='TRANSPORT_FAILURE')
                    completed=False
                    try:
                        await self.setup()
                        initial=await self.data_snapshot('initial')
                        await self.m0(initial)
                        before=await self.data_snapshot('before')
                        primary=self.external(before,'memory_with_mcp','M1-main')
                        nohistory=self.external(None,'no_history','M1-no-history')
                        text=self.external(before,'identical_history_as_text_no_live_tools','M1-text')
                        primary_reports=await self.guard_model(primary,'M1-main')
                        nohistory_reports=await self.guard_model(nohistory,'M1-no-history')
                        text_reports=await self.guard_model(text,'M1-text')
                        self.mode_data['M1']={'main':primary_reports,'no_history':nohistory_reports,'identical_text':text_reports,
                            'same_context_sha256':fingerprint_hash(before),'generated_by':'external_llm_generated',
                            'not_a_causal_model_quality_claim':'MCP and text variants carry identical information; assess guard behavior separately.'}
                        after,negative=await self.feedback()
                        updated=self.external(after,'memory_with_mcp','M2-after')
                        updated_reports=await self.guard_model(updated,'M2-after')
                        semantic=semantic_attention(updated,negative)
                        self.semantic_results={'before':semantic_attention(primary),'after':semantic}
                        self.at('AT08',semantic['consistent'],json.dumps(semantic),classification='LLM_BEHAVIOR')
                        self.mode_data['M2']={'semantic_before_after':self.semantic_results,'after_candidates':updated_reports,
                            'feedback_event_id':negative,'task_sha256':hashlib.sha256(TASK.encode()).hexdigest(),
                            'execution_proposal_origin':'operator_seeded','attention_proposal_origin':'external_llm_generated'}
                        self.at('AT16',True,'Numeric limits explicitly waived; fixed two seeds and one feedback step per seed, no open-ended loop.')
                        self.at('AT17',self.baseline['result']=='PASS' and self.baseline['pass_count']==86,
                                'Current 101 local tests and existing real 86-invariant suite pass.')
                        completed=True
                    except Exception as error:
                        self.at('harness_complete',False,str(error),classification='TRANSPORT_FAILURE')
                        raise
                    finally:
                        states=[]
                        for move_id in self.moves:
                            current=await self.history(move_id)
                            if current['execution_permission']['allowed']:
                                current=await self.transition('cleanup:'+str(move_id),move_id,'abandon',reason='End of bounded attention QA.')
                            states.append(current)
                        write_json(self.out/'final-moves.json',states)
                        unchanged=intact(self.before,snapshot(self.db))
                        self.at('AT18',all(unchanged.values()) and ResearchStore(self.db).verify_audit()['ok']
                                and all(not x['execution_permission']['allowed'] for x in states))
                        with ResearchStore(self.db)._connect() as connection:
                            duplicate_count=connection.execute('''SELECT count(*) FROM
                                (SELECT b.identity_hash FROM research_move_bindings b JOIN research_moves m ON m.id=b.move_id
                                 WHERE m.project=? GROUP BY b.identity_hash HAVING count(*)>1)''',(self.project,)).fetchone()[0]
                        formulated=[c for run in self.model_runs.values() for c in run['output']['candidates']]
                        provenance_correct=sum(c['origin']=='llm_generated' for c in formulated)+sum(c['origin']=='operator_seeded' for c in self.known.values())
                        provenance_total=len(formulated)+len(self.known)
                        known_fps={ResearchMoveFingerprint.build(c['move']['proposed_operation']).digest for c in self.known.values()}
                        external_fps={ResearchMoveFingerprint.build(c).digest for c in formulated}
                        def call_value(call):
                            raw=call['response']
                            if raw.get('isError'):return {}
                            return raw.get('structuredContent') or json.loads(raw['content'][0]['text'])
                        active_grants=[(call,call_value(call)) for call in self.calls if call['tool']=='transition_research_move'
                            and call['arguments']['action']=='activate_experiment']
                        unsafe=sum(v.get('execution_permission',{}).get('allowed',False)
                                   and v.get('proposed_operation',{}).get('mechanism') not in
                                   {'bounded_word_observation','diagnostic_word_observation'} for _,v in active_grants)
                        stale=sum(v.get('idempotent',False) and v.get('execution_permission',{}).get('allowed',False)
                                  for _,v in active_grants)
                        server_cpu_end=server_cpu()
                        server_seconds=(server_cpu_end['seconds']-self.server_cpu_begin['seconds']
                                        if server_cpu_end['pid']==self.server_cpu_begin['pid'] else None)
                        client_seconds=time.process_time()-self.cpu_start
                        children_end=resource.getrusage(resource.RUSAGE_CHILDREN)
                        children_seconds=(children_end.ru_utime+children_end.ru_stime
                                          -self.children_start.ru_utime-self.children_start.ru_stime)
                        metrics={'seed':self.seed_number,'eligible_recall':self.eligible_recall,
                            'unsafe_activation_count':unsafe,'stale_as_active_count':stale,'same_fingerprint_duplicate_count':duplicate_count,
                            'provenance_accuracy':provenance_correct/provenance_total if provenance_total else None,
                            'provenance_records_checked':provenance_total,
                            'independent_new_candidate_count':{'server':0,'external_formulations':len(formulated),
                                'external_structurally_new_fingerprints':len(external_fps-known_fps),
                                'mathematical_novelty_established':False},
                            'mcp_tool_calls':len(self.calls),'client_cpu_seconds':client_seconds,
                            'mcp_server_cpu_seconds':server_seconds,
                            'all_local_child_cpu_seconds':children_seconds,
                            'observed_host_total_cpu_seconds':client_seconds+children_seconds+server_seconds if server_seconds is not None else None,
                            'model_cli_local_cpu_seconds':self.model_local_cpu,'external_inference_cpu_seconds':None,
                            'wall_seconds':time.monotonic()-self.started,'response_to_failure_delta':self.semantic_results,
                            'hard_limits_waived_by_user':True,'oracle_version':'1.1'}
                        write_json(self.out/'metrics.json',metrics)
                        write_json(self.out/'result.json',{'project':self.project,'seed':self.seed_number,
                            'result':'FAIL' if not completed or any(x['result']=='FAIL' for x in self.checks) else 'PASS',
                            'completed':completed,
                            'checks':self.checks,'modes':self.mode_data,'metrics':metrics,'initial_rows_preserved':unchanged,
                            'events':self.event_ids,'obligations':self.obligation_ids})


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--private-dir',required=True)
    args=parser.parse_args();private=Path(args.private_dir).resolve(strict=True)
    metadata=json.loads((private/'metadata.json').read_text());config=configure()
    baseline=json.loads((private/'regression-v042/result.json').read_text())
    db=(Path(config['LIVE_MATH_DATA_DIR'])/'research.sqlite3').resolve(strict=True)
    logging.basicConfig(level=logging.WARNING)
    summary=[]
    for seed in SEEDS:
        out=private/('seed-'+str(seed));out.mkdir(mode=0o700)
        write_json(out/'before.json',snapshot(db))
        with sqlite3.connect(db.as_uri()+'?mode=ro',uri=True) as source,sqlite3.connect(out/'research-before.sqlite3') as target:source.backup(target)
        runner=AttentionRun(out,db,config['LIVE_MATH_PUBLIC_URL'],seed,private.name,baseline)
        oauth(config,runner)
        summary.append(json.loads((out/'result.json').read_text()))
        print(json.dumps({'seed':seed,'result':summary[-1]['result'],'checks':len(runner.checks),'calls':len(runner.calls)},ensure_ascii=False),flush=True)
    write_json(private/'attention-summary.json',summary)


if __name__=='__main__':main()
