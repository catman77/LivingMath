"""Additional live acceptance cases; operator actions are confined to the QA project."""
import copy
import json
from pathlib import Path
import sqlite3

from research_store import ResearchStore


class V042Cases:
    def operation_count(self):
        with sqlite3.connect(self.db.as_uri()+'?mode=ro',uri=True) as connection:
            return connection.execute('SELECT count(*) FROM operations').fetchone()[0]

    async def completion_boundaries(self,move_id):
        good={'outcome':'ERROR','summary':'Controlled negative request.'}
        for name,result in [('empty',{}),('bad-outcome',{'outcome':'VERIFIED','summary':'Not a permitted outcome'}),
                            ('blank-summary',{'outcome':'SUCCESS','summary':' '})]:
            before=self.operation_count()
            answer=await self.transition('boundary:'+name,move_id,'complete',allow_error=True,
                reason='Invalid result control.',evidence_refs=['event:'+str(self.ids['source_event'])],result=result)
            self.check('result:'+name+':rejected_without_operations',answer is None and self.operation_count()==before)
        for name,refs in [('unregistered-artifact',['artifact:does-not-exist']),('missing-event',['event:999999999']),
                          ('foreign-event',['event:2']),('malformed-event',['event:'+str(self.ids['source_event'])+'junk'])]:
            before=self.operation_count()
            answer=await self.transition('boundary:'+name,move_id,'complete',allow_error=True,
                reason='Invalid witness control.',evidence_refs=refs,result=good)
            self.check('evidence:'+name+':rejected_without_operations',answer is None and self.operation_count()==before)

    async def additional_outcomes(self):
        for outcome in ('FAILURE','INCONCLUSIVE','ERROR'):
            name='outcome_'+outcome.lower()
            request=self.proposal('byte_length '+outcome.lower()+' control',
                len(self.fixture)+1 if outcome=='FAILURE' else 'outcome declaration only')
            record=await self.propose(name,request)
            await self.audit(name,record['id'])
            await self.transition(name+':activate',record['id'],'activate_experiment')
            if outcome=='FAILURE':
                data={'expected':len(self.fixture)+1,'observed':len(self.fixture),'matches':False}
            elif outcome=='INCONCLUSIVE':
                data={'observed':len(self.fixture),'independent_repeat_available':False,'conclusion':'undetermined'}
            else:
                try:self.fixture.index(b'absent-controlled-pattern')
                except ValueError as error:data={'exception':type(error).__name__,'message':str(error)}
            done=await self.complete(name,record['id'],'byte_length '+outcome.lower()+' control',data,outcome=outcome)
            self.check('outcome:'+outcome+':completed_unverified',done['status']=='COMPLETED'
                and done['completion']['result']['outcome']==outcome and not done['completion']['legacy']
                and done['proof_status']=='unverified' and not done['execution_permission']['allowed'])
            last=next(call for call in reversed(self.calls) if call['tool']=='transition_research_move'
                      and call['arguments']['action']=='complete')
            original=copy.deepcopy(last['arguments'])
            before=self.operation_count()
            replay=await self.call('transition_research_move',original)
            self.check('idempotency:'+outcome+':no_duplicate_operations',replay['idempotent'] and self.operation_count()==before)
            original['result']['summary']='Tampered result under an already completed key'
            tamper=await self.call('transition_research_move',original,allow_error=True)
            self.check('idempotency:'+outcome+':result_cannot_be_replaced',tamper is None and self.operation_count()==before)

    def operator_disposition(self,event_id,request,disposition,name,evidence_event=None):
        payload={'project':self.project,'event_id':event_id,'obligation_id':self.ids['obligation'],
            'expected_version':self.frontier_version,'proposed_operation':request['proposed_operation'],
            'disposition':disposition,'reason':'User-authorized QA '+disposition+': exact fixed fixture and scoped claims only.',
            'evidence_refs':['event:'+str(evidence_event or self.ids['source_event'])],
            'request_key':self.project+':review:'+name,'operator':'User-authorized isolated QA operator'}
        record=ResearchStore(self.db).evidence_reviews.record(**payload)
        path=self.out/('operator-review-'+name+'.json')
        path.write_text(json.dumps({'request':payload,'response':record},ensure_ascii=False,indent=2)+'\n')
        self.ids['review_'+name]=record['id']
        before=self.operation_count()
        duplicate=ResearchStore(self.db).evidence_reviews.record(**payload)
        self.check('operator:'+name+':idempotent',duplicate['id']==record['id'] and self.operation_count()==before)
        return record

    async def advisory(self,request,project=None):
        fields={k:v for k,v in request.items() if k not in {'scope','active_frontier_version','proposal','fingerprint'}}
        return await self.call('audit_research_shift',{'project':project or self.project,**fields})

    async def adverse_boundaries(self):
        event_id=self.ids['contradictory_evidence']
        diagnostic=self.proposal('byte_length diagnostic','Identify the mismatching earlier reading only')
        diagnostic['parent_event_ids'].append(event_id)
        diagnostic['evidence_refs'].append('event:'+str(event_id))
        diagnostic['evidence_roles']={str(event_id):{'role':'diagnostic_subject',
            'reason':'Study the failed reading as an object; it is not a supporting premise of the new claim.'}}
        report=await self.advisory(diagnostic)
        self.check('adverse:role_label_alone_cannot_clear_conflict','ADVERSE_EVIDENCE_REQUIRES_REVIEW' in report['warnings'])
        self.operator_disposition(event_id,diagnostic,'diagnostic_subject','diagnostic')
        record=await self.propose('diagnostic_move',diagnostic)
        audited=await self.audit('diagnostic',record['id'])
        self.check('adverse:diagnostic_can_be_audited',audited['status']=='AUDITED'
            and audited['audit']['adverse_evidence'][0]['status']=='SCOPED_DISPOSITION')
        granted=await self.transition('diagnostic:activate',record['id'],'activate_experiment')
        self.check('adverse:diagnostic_experiment_allowed',granted['execution_permission']['allowed'])
        changed=copy.deepcopy(diagnostic)
        changed['proposed_operation']['testable_consequence']='Use the earlier contradiction as a true supporting premise'
        report=await self.advisory(changed)
        self.check('adverse:disposition_does_not_cross_claims','ADVERSE_EVIDENCE_REQUIRES_REVIEW' in report['warnings'])
        updated=await self.call('research_obligation_update',{'project':self.project,'obligation_id':self.ids['obligation'],
            'expected_version':self.frontier_version,'changes':{'status':'OPEN'}})
        self.frontier_version=updated['version']
        stale=await self.audit('diagnostic-stale-review',record['id'])
        self.check('adverse:disposition_expires_with_frontier_version',stale['status']=='REQUIRES_REVIEW'
            and not stale['execution_permission']['allowed'])
        self.operator_disposition(event_id,diagnostic,'diagnostic_subject','diagnostic-renewed')
        audited=await self.audit('diagnostic-renewed',record['id'])
        granted=await self.transition('diagnostic:reactivate',record['id'],'activate_experiment')
        self.check('adverse:renewed_scoped_review_allows_progress',audited['status']=='AUDITED' and granted['execution_permission']['allowed'])
        await self.complete('diagnostic',record['id'],'byte_length diagnostic',len(self.fixture))

        mislabeled=await self.event('mislabeled_event',{'fixture_sha256':self.fixture_hash,'observed':len(self.fixture),
            'control':'Adverse label intentionally incorrect in this QA case; the source row will not be edited.'},
            kind='failed_check',status='refuted')
        correction=await self.event('label_correction_evidence',{'fixture_sha256':self.fixture_hash,'observed':len(self.fixture),
            'corrects_event_id':mislabeled,'software_qa_only':True})
        request=self.proposal('byte_length label correction',len(self.fixture))
        request['parent_event_ids'].append(mislabeled)
        request['evidence_refs'].append('event:'+str(mislabeled))
        request['evidence_roles']={str(mislabeled):{'role':'label_error','reason':'Scope-specific correction supported by an independent QA observation event.'}}
        record=await self.propose('label_correction_move',request)
        self.check('adverse:uncleared_mislabel_requires_review',record['status']=='REQUIRES_REVIEW')
        with sqlite3.connect(self.db.as_uri()+'?mode=ro',uri=True) as connection:
            before=connection.execute('SELECT * FROM events WHERE id=?',(mislabeled,)).fetchone()
        self.operator_disposition(mislabeled,request,'label_error','label-correction',correction)
        await self.audit('label-correction',record['id'])
        granted=await self.transition('label-correction:activate',record['id'],'activate_experiment')
        self.check('adverse:mislabel_can_be_cleared_scoped',granted['execution_permission']['allowed'])
        await self.complete('label-correction',record['id'],'byte_length label correction',len(self.fixture))
        with sqlite3.connect(self.db.as_uri()+'?mode=ro',uri=True) as connection:
            after=connection.execute('SELECT * FROM events WHERE id=?',(mislabeled,)).fetchone()
        self.check('adverse:label_correction_preserves_source_history',before==after)

    async def legacy_replay(self):
        root=Path(__file__).resolve().parents[1]
        prior=root/'docs/qa/v0.4.1-positive-20261026T061543Z/calls.json'
        calls=json.loads(prior.read_text())
        original=calls[38]['arguments']
        report=await self.advisory(original['move'],project=original['project'])
        finding=next((f for f in report['findings'] if f['code']=='ADVERSE_EVIDENCE_REQUIRES_REVIEW'),{})
        self.check('adverse:original_event22_blocks_original_move10',22 in finding.get('source_event_ids',[])
            and report['verdict']=='REQUIRES_SEMANTIC_REVIEW' and not report['execution_permission']['allowed'])
        before=self.operation_count()
        legacy=await self.call('transition_research_move',calls[36]['arguments'])
        self.check('legacy:historical_completed_unchanged',legacy['status']=='COMPLETED'
            and legacy['completion']['legacy'] and legacy['idempotent'] and self.operation_count()==before)
        new_result=copy.deepcopy(calls[36]['arguments'])
        new_result['result']={'outcome':'SUCCESS','summary':'Must not replace historical outcome under its old key'}
        denied=await self.call('transition_research_move',new_result,allow_error=True)
        self.check('legacy:result_cannot_be_added_under_old_key',denied is None and self.operation_count()==before)
