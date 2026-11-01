"""Artifact task actions in the existing durable Controller and DAV Store.

No study runners, fixed tasks, baseline archives, ready models or client-authored
premises enter this path. All computation is internal, bounded and unverified.
"""
import hashlib
import json

from davcore.ast import canonical, digest
from semantic_repair.context009 import packets, resolve
from semantic_repair.runtime009 import assemble
from semantic_repair.source import ObligationQueue
from semantic_repair.worker import call

from .artifact_contract import ArtifactInput


def source(controller, project: str, ref):
    context=resolve(controller.service.store,project,ref.id)
    p=context.record['payload']
    if p['sha256']!=ref.sha256 or p['version']!=ref.version:raise ValueError('STALE_OR_SUBSTITUTED_SNAPSHOT_REFERENCE')
    return context


def ingest(controller, project: str, packet: ArtifactInput, request_key: str, provenance=None) -> dict:
    from .contract import Problem
    controller.service.project(project)
    if not isinstance(request_key,str) or not request_key.strip() or len(request_key)>200:
        raise ValueError('EXPLICIT_REQUEST_KEY_REQUIRED')
    identity={'input':packet.model_dump(),'provenance':provenance or {'kind':'AUTHENTICATED_MCP_ARTIFACT_INPUT'}}
    key='artifact-input:'+digest(request_key)
    existing=controller.service.store.repeated(project,key,identity)
    if existing:
        row=existing
    else:
        if packet.snapshot:
            ctx=source(controller,project,packet.snapshot);snapshot=ctx.record
            if any(getattr(packet,k) is not None and ctx.record['payload'][k]!=getattr(packet,k) for k in ('source_name','edition','language')):
                raise ValueError('SNAPSHOT_METADATA_SUBSTITUTION')
            if packet.rights is not None and packet.rights.model_dump()!=ctx.record['payload']['rights']:
                raise ValueError('SNAPSHOT_RIGHTS_METADATA_SUBSTITUTION')
        else:
            raw=packet.raw_text
            assert raw is not None
            assert packet.rights is not None
            sha=hashlib.sha256(raw.encode()).hexdigest()
            if packet.expected_sha256 is not None and sha!=packet.expected_sha256:raise ValueError('SOURCE_SHA256_MISMATCH')
            previous=source(controller,project,packet.replaces_snapshot) if packet.replaces_snapshot else None
            namespace=previous.record['payload']['namespace'] if previous else digest([project,packet.source_name,packet.edition,key])
            version=previous.record['payload']['version']+1 if previous else 1
            if previous and not current_source(controller,previous):raise ValueError('SOURCE_VERSION_BRANCH_REQUIRES_CURRENT_PARENT')
            snapshot=controller.journal.append(project,'artifact_source','artifact-source:'+digest(identity),identity,
                {'raw_text':raw,'sha256':sha,'namespace':namespace,'version':version,'source_name':packet.source_name,
                    'edition':packet.edition,'language':packet.language,'rights':packet.rights.model_dump(),
                    'previous_snapshot_id':previous.record['id'] if previous else None,
                    'original_bytes_preserved':True,'source_assurance':'DECLARED_RIGHTS_NOT_AUTHOR_ENDORSEMENT'})
        problem=Problem(kind='artifact_reconstruction',scope=packet.scope,
            source_refs=['dav:'+str(snapshot['id'])],artifact_snapshot_id=snapshot['id'],
            artifact_profile=packet.profile,artifact_budget=packet.budget,
            artifact_interpretation=packet.interpretation)
        row=controller.journal.append(project,'automation_artifact_input',key,identity,
            {'input':packet.model_dump(exclude={'raw_text'}),'source_id':snapshot['id'],'problem':problem.model_dump()})
    problem=Problem.model_validate(row['payload']['problem'])
    case=controller.submit(project,problem,[row['id'],row['payload']['source_id']])
    ctx=resolve(controller.service.store,project,row['payload']['source_id'])
    return {'input_id':row['id'],'case_ids':[case['id']],'source_snapshot':{
        'id':ctx.record['id'],'version':ctx.public()['version'],'sha256':ctx.public()['sha256']},
        'status':'ACCEPTED_FOR_AUTOMATIC_PROCESSING','input_assurance':'DECLARED_NOT_INDEPENDENTLY_VERIFIED',
        'proof_status':'unverified','execution_permission':{'allowed':False}}


def current_source(controller, context) -> bool:
    return not any(r['payload']['namespace']==context.public()['namespace'] and r['payload']['version']>context.public()['version']
        for r in controller.journal.rows(('artifact_source',),context.project))


def rows(controller, case: dict, kind: str) -> list[dict]:
    return controller.journal.rows((kind,),case['project'],case_id=case['id'])


async def worker(controller, case, state, action_key, mode, payload, context):
    key=f"artifact:{case['id']}:g{state['generation']}:{action_key}"
    identity={'action':mode,'input':payload,'source':context.public(),'policy':controller.binding}
    old=controller.service.store.repeated(case['project'],key,identity)
    if old:return old
    budget=case['payload']['problem']['artifact_budget'];attempts=rows(controller,case,'artifact_worker_attempt')
    same=[r for r in attempts if r['payload']['action_key']==key]
    if len(attempts)>=budget['workers'] or len(same)>budget['retries']:raise ValueError('ARTIFACT_WORKER_BUDGET_EXHAUSTED')
    controller.journal.append(case['project'],'artifact_worker_attempt',key+':attempt:'+str(len(same)),
        {'case_id':case['id'],'action_key':key,'attempt':len(same)},
        {'case_id':case['id'],'action_key':key,'mode':mode,'attempt':len(same),'generation':state['generation']})
    result=await call(mode,payload,context=context if mode.startswith('artifact_') else None)
    return controller.journal.append(case['project'],'artifact_checkpoint',key,identity,
        {'case_id':case['id'],'generation':state['generation'],'result':result,'source_context':context.public(),
            'coordinator_binding':controller.binding,'action':mode})


def observations(controller, case, state):
    return [controller.service.store.get(case['project'],i)['payload']['result'] for i in state.get('observation_ids',[])]


async def advance(controller, case: dict, last: dict, state: dict, problem, control_id) -> None:
    ctx=resolve(controller.service.store,case['project'],problem.artifact_snapshot_id)
    windows,source_losses=packets(ctx);status=last['payload']['status'];budget=problem.artifact_budget
    publish=lambda:controller._can_publish(case,last,state['basis'],control_id)
    step=lambda status,state,result=None:controller.journal.step(case,last,status,state,result)
    if not current_source(controller,ctx):
        step('REQUIRES_REVIEW',state,{'outcome':'STALE_SOURCE_VERSION','historical_results_retained':True});return
    if status=='DIAGNOSING':
        step('PROPOSING',{**state,'observation_ids':[],'result_ids':[],'revision':0,'next_window':0,
            'source_reads':0,'models_used':0,'source_losses':source_losses,
            'pending_action':{'kind':'READ_SOURCE_WINDOW','window':0,
                'strategy':('meaning014/1' if problem.artifact_interpretation == 'meaning014' else 'observer013/1' if problem.artifact_interpretation == 'observer013' else 'observer012/1' if problem.artifact_interpretation == 'observer012' else 'general011/1') if problem.artifact_interpretation else 'artifact009/1'}},
            {'outcome':'RAW_SOURCE_REGISTERED','source_context':ctx.public(),'worker_caps':{'CPU_s':5,'wall_s':6,'AS_MiB':512,'input_bytes':64000,'output_bytes':256000}})
        return
    if status=='PROPOSING':
        action=state['pending_action'];index=action['window']
        if index>=len(windows):
            finish(controller,case,last,state,ctx,'NO_SUPPORTED_SOURCE_WINDOW');return
        if state['source_reads']>=budget.source_views:
            finish(controller,case,last,state,ctx,'SOURCE_VIEW_BUDGET_EXHAUSTED');return
        if problem.artifact_interpretation and action['strategy'].startswith(('general011', 'observer012', 'observer013', 'meaning014')):
            from .semantic011 import observe_source
            row = await observe_source(controller, case, state, windows[index], action, ctx)
        else:
            row=await worker(controller,case,state,'read:'+str(state['source_reads']),'observe',
                {'packet':windows[index],'strategy':action['strategy']},ctx)
        if not publish():return
        step('AUDITING',{**state,'observation_ids':state['observation_ids']+[row['id']],
            'source_reads':state['source_reads']+1,'next_window':max(state['next_window'],index+1)},
            {'outcome':'ADDRESSED_RAW_OBSERVATION','observation_id':row['id'],'action':action})
        return
    if status=='AUDITING':
        plan=assemble(observations(controller,case,state),case['project'])
        identity={'case_id':case['id'],'generation':state['generation'],'revision':state['revision'],
            'observations':state['observation_ids'],'source':ctx.public(),'coordinator_binding':controller.binding}
        row=controller.journal.append(case['project'],'artifact_plan',f"artifact-plan:{case['id']}:g{state['generation']}:r{state['revision']}",identity,
            {'case_id':case['id'],**identity,**plan,'source_losses':source_losses})
        step('EXPERIMENTING',{**state,'plan_id':row['id'],'plan_cursor':0,'revision_result_ids':[]},
            {'outcome':'CONDITIONAL_FAMILY_ENUMERATED','plan_id':row['id'],'model_candidates':len(plan['plans'])})
        return
    plan=controller.service.store.get(case['project'],state['plan_id'])['payload']
    if status=='EXPERIMENTING':
        if state['plan_cursor']>=len(plan['plans']):
            revise_or_finish(controller,case,last,state,ctx,windows,plan);return
        if state['models_used']>=budget.models:
            finish(controller,case,last,state,ctx,'MODEL_BUDGET_EXHAUSTED');return
        if len(rows(controller, case, 'artifact_worker_attempt')) + 2 > budget.workers:
            finish(controller, case, last, state, ctx, 'ARTIFACT_WORKER_BUDGET_EXHAUSTED');return
        item=plan['plans'][state['plan_cursor']]
        try:
            row=await worker(controller,case,state,f"r{state['revision']}:compile:{state['plan_cursor']}",'artifact_compile',
                {'premises':item['premises'],'binding':item['binding'],'profile':problem.artifact_profile},ctx)
        except ValueError as exc:
            unsupported=next((code for code in ('NEGATIVE_INPUT_NOT_SUPPORTED_IN_THIS_SLICE',
                'NEGATIVE_FORWARD_REQUIRES_OWN_SIGNED_SLICE','MIXED_REALIZATION_REQUIRES_LOCAL_SLICE',
                'WORKER_INPUT_BOUND') if code in str(exc)),None)
            if unsupported is None:raise
            step('EXPERIMENTING',{**state,'plan_cursor':state['plan_cursor']+1,'models_used':state['models_used']+1,
                'source_losses':state['source_losses']+[{'reason':unsupported,'slice_id':item['slice_id'],
                    'source_refs':sorted({r for p in item['premises'] for r in p['source_refs']})}]},
                {'outcome':'UNSUPPORTED_LOCAL_SLICE_RETAIN_OTHER_SLICES','reason':unsupported})
            return
        if not publish():return
        model={k:v for k,v in row['payload']['result'].items() if k!='isolation'}
        if model['status'] not in {'COMPILED_CONDITIONAL_MODEL', 'META_ONLY_SOURCE_MODEL'}:
            step('EXPERIMENTING',{**state,'plan_cursor':state['plan_cursor']+1,'models_used':state['models_used']+1,
                'source_losses':state['source_losses']+[{'reason':model['status'],'slice_id':item['slice_id']}]},
                {'outcome':'LOCAL_SLICE_UNSUPPORTED','checkpoint_id':row['id']});return
        step('CHECKING',{**state,'compiled_checkpoint_id':row['id'],'models_used':state['models_used']+1},
            {'outcome':'QUERY_FREE_MODEL_FROZEN','model_hash':model['compiled_hash']});return
    if status=='CHECKING':
        item=plan['plans'][state['plan_cursor']]
        compiled=controller.service.store.get(case['project'],state['compiled_checkpoint_id'])
        model={k:v for k,v in compiled['payload']['result'].items() if k!='isolation'}
        try:
            check=await worker(controller,case,state,f"r{state['revision']}:check:{state['plan_cursor']}",'artifact_check',
                {'premises':item['premises'],'binding':item['binding'],'profile':problem.artifact_profile,'model':model},ctx)
        except ValueError as exc:
            if 'WORKER_INPUT_BOUND' not in str(exc):raise
            step('EXPERIMENTING', {**state, 'plan_cursor': state['plan_cursor'] + 1,
                'source_losses': state['source_losses'] + [{'reason': 'CHECKER_ENVELOPE_INPUT_BOUND',
                    'slice_id': item['slice_id'], 'compiled_checkpoint_id': compiled['id']} ]},
                {'outcome': 'UNCHECKED_MODEL_RETAINED_WITHOUT_CERTIFICATE'})
            return
        if not publish():return
        result=controller.journal.append(case['project'],'artifact_result',
            f"artifact-result:{case['id']}:g{state['generation']}:r{state['revision']}:{state['plan_cursor']}",
            {'compiler_checkpoint':compiled['id'],'checker_checkpoint':check['id'],'source':ctx.public(),'binding':item['binding']},
            {'case_id':case['id'],'generation':state['generation'],'revision':state['revision'],'slice_id':item['slice_id'],
                'source_context':ctx.public(),'coordinator_binding':controller.binding,'model':model,'binding':item['binding'],
                'premises':item['premises'],'compiler_checkpoint_id':compiled['id'],'checker_checkpoint_id':check['id'],
                'check':{k:v for k,v in check['payload']['result'].items() if k!='isolation'}})
        step('EXPERIMENTING',{**state,'plan_cursor':state['plan_cursor']+1,
            'result_ids':state['result_ids']+[result['id']],
            'revision_result_ids':state['revision_result_ids']+[result['id']]},
            {'outcome':'SCOPED_RESULT_APPENDED','artifact_result_id':result['id']})


def revise_or_finish(controller, case, last, state, ctx, windows, plan):
    obs=observations(controller,case,state)
    checked=[controller.service.store.get(case['project'],i) for i in state['revision_result_ids']]
    obligations=[];actions=[]
    guarded=[r for r in checked if r['payload']['model']['observer']['kind']=='GUARDED_TRANSFORMATION']
    general = case['payload']['problem'].get('artifact_interpretation') in {'general011', 'observer012', 'observer013', 'meaning014'}
    if general and state['next_window'] >= len(windows):
        from .semantic011 import attention_actions
        extra_obligations, extra_actions = attention_actions(obs, windows, state)
        obligations.extend(extra_obligations)
        actions.extend(extra_actions)
    if guarded and not any(r['payload']['check']['analysis']['outcome']=='HAS_ENABLED_TRACE' for r in guarded):
        obligations.append({'kind':'UNBOUND_FORMAL_MIDDLE'})
        for index,w in enumerate(windows[:state['next_window']]):
            relevant=any(o['source_packet']['id']==w['id'] and any(s['kind']=='GUARDED_TRANSFORMATION' for s in o['slices']) for o in obs)
            if relevant and not any(o['observer']=='artifact009-middle/1' and o['source_packet']['id']==w['id'] for o in obs):
                actions.append({'id':'middle:'+str(index),'window':index,'strategy':'artifact009-middle/1','covers':['UNBOUND_FORMAL_MIDDLE'],'cost':0})
    if state['next_window']<len(windows):
        obligations.append({'kind':'UNCOVERED_SOURCE_WINDOW'})
        actions.append({'id':'window:'+str(state['next_window']),'window':state['next_window'],
            'strategy':('meaning014/1' if case['payload']['problem'].get('artifact_interpretation') == 'meaning014' else 'observer013/1' if case['payload']['problem'].get('artifact_interpretation') == 'observer013' else 'observer012/1' if case['payload']['problem'].get('artifact_interpretation') == 'observer012' else 'general011/1') if general else 'artifact009/1',
            'covers':['UNCOVERED_SOURCE_WINDOW'],'cost':1})
    queue=ObligationQueue(4);queue.executed=state['source_reads'];choice=queue.choose(obligations,actions)
    if state.get('prior_revision_result_ids'):
        before=[controller.service.store.get(case['project'],i) for i in state['prior_revision_result_ids']]
        def fingerprint(rs):
            return sorted((r['payload']['check']['analysis'].get('source_transition_analysis', {}).get(
                    'semantic_projection_sha256', r['payload']['model']['target_projection_hash']),
                r['payload']['check']['analysis'].get('source_transition_analysis', {}).get(
                    'independent_full_table_sha256', r['payload']['check']['analysis']['operation_table_sha256']),
                r['payload']['check']['analysis']['outcome']) for r in rs)
        controller.journal.append(case['project'],'artifact_revision',f"artifact-revision:{case['id']}:g{state['generation']}:r{state['revision']}",
            {'case_id':case['id'],'previous_result_ids':state['prior_revision_result_ids'],'current_result_ids':state['revision_result_ids']},
            {'case_id':case['id'],'revision':state['revision'],'previous_result_ids':state['prior_revision_result_ids'],
                'current_result_ids':state['revision_result_ids'],
                'effect':'EXECUTABLE_PROJECTION_CHANGED' if fingerprint(before)!=fingerprint(checked) else 'NO_SEMANTIC_CHANGE',
                'historical_results_retained':True})
    if 'action' in choice and state['source_reads']<case['payload']['problem']['artifact_budget']['source_views']:
        controller.journal.step(case,last,'PROPOSING',{**state,'revision':state['revision']+1,
            'pending_action':choice['action'],'prior_revision_result_ids':state['revision_result_ids']},{'outcome':'I_T_ATTENTION_REVISION','semantic_change':'PENDING_COMPUTATION','computed_obligations':obligations,
                'selected_action':choice,'previous_result_ids':state['revision_result_ids'],'old_certificates_retained':True})
    else:finish(controller,case,last,state,ctx,choice.get('stop','SOURCE_VIEW_BUDGET_EXHAUSTED'))


def finish(controller,case,last,state,ctx,reason):
    results=[controller.service.store.get(case['project'],i) for i in state['result_ids']]
    latest=max((r['payload']['revision'] for r in results),default=-1)
    final=[r for r in results if r['payload']['revision']==latest]
    observed=observations(controller,case,state);plan=assemble(observed,case['project'])
    all_packets,source_losses=packets(ctx)
    visible={s['id'] for p in all_packets for s in p['spans']}
    covered={ref for r in final for p in r['payload']['premises'] for ref in p['source_refs']}
    unknown=sorted(visible-covered)
    spans=sorted((s for p in all_packets for s in p['spans'] if s['id'] not in covered),key=lambda s:s['start'])
    ranges=[]
    for span in spans:
        if ranges and span['start']-ranges[-1]['end']<=2:
            ranges[-1].update(end=span['end'],last_ref=span['id'])
        else:ranges.append({'start':span['start'],'end':span['end'],'first_ref':span['id'],'last_ref':span['id']})
    planned={digest([p['slice_id'],p['binding']['id']]) for p in plan['plans']}
    checked={digest([r['payload']['slice_id'],r['payload']['binding']['id']]) for r in final}
    family_complete=bool(planned) and planned<=checked
    if planned and not family_complete:
        state={**state,'source_losses':state['source_losses']+[{'reason':'INCOMPLETE_CHECKED_FAMILY',
            'planned_branches':len(planned),'checked_branches':len(checked)}]}
    outcome='PARTIAL_MODEL' if final else 'UNSUPPORTED_ARTIFACT'
    source_partial = {}
    if not final and case['payload']['problem'].get('artifact_interpretation') in {'general011', 'observer012', 'observer013', 'meaning014'}:
        retained = []
        for ident in state['observation_ids']:
            view = controller.service.store.get(case['project'], ident)['payload']['result']
            grounded = {r['reading_id'] for r in view.get('source_alignment', {}).get('relations', [])
                if r['exact_citations']}
            if grounded:
                retained.append({'checkpoint_id': ident, 'reading_ids': sorted(grounded)})
        if retained:
            outcome = 'SOURCE_GRAPH_PARTIAL'
            source_partial = {'source_reading_refs': retained,
                'source_annotation_status': 'ADDRESSED_HYPOTHESES_NOT_TYPED008_NETWORK',
                'target_compilation': 'NOT_ESTABLISHED; admission guards and losses retained'}
    # Complete coverage means all addressed nonempty source lines are represented;
    # it still never means complete human semantics or a physical model.
    if final and family_complete and not unknown and not source_losses and not plan['losses'] and not state['source_losses']:outcome='BOUNDED_CONDITIONAL_MODEL'
    v012 = case['payload']['problem'].get('artifact_interpretation') in {'observer012','observer013','meaning014'}
    meta_ids = [r['id'] for r in final if r['payload']['model'].get('target_model') == 'NOT_APPLICABLE']
    extras = {}
    if v012:
        from semantic_repair.check012 import hypothesis_families
        extras = {'meta_only_result_ids': meta_ids, 'target_model_result_ids': [r['id'] for r in final if r['id'] not in meta_ids],
            'hypothesis_families': hypothesis_families(final), 'independent_source_evidence_count': 0,
            'source_verified': False, 'full_formalization': False}
        if final and len(meta_ids) == len(final): outcome = 'SOURCE_META_FORMALIZATION'
    if case['payload']['problem'].get('artifact_interpretation') == 'meaning014':
        from .semantic014 import summary
        extras.update(summary(controller,case))
        if not final and any(r['available'] for r in extras['baseline_A0_refs']): outcome='READABLE_A0_WITH_UNRESOLVED_SOURCE_MODEL'
        if not final and not any(r['available'] for r in extras['baseline_A0_refs']) and any(r['status']=='COST_BOUND' for r in extras['source_backend_statuses']): outcome='COST_BOUND'
    controller.journal.step(case,last,'COMPLETED',state,{'outcome':outcome, **extras,**source_partial,'stop_reason':reason,'source_context':ctx.public(),
        'artifact_result_ids':[r['id'] for r in final],'all_revision_result_ids':state['result_ids'],
        'coverage':{'covered_refs':sorted(covered),'unsupported_or_unparsed_refs':unknown[:256],
            'unsupported_ref_count':len(unknown),'unsupported_refs_truncated':len(unknown)>256,
            'unsupported_byte_ranges':ranges,'source_ranges':source_losses,
            'whole_artifact_semantics':'NOT_ESTABLISHED'},'losses':plan['losses']+state['source_losses'],
        'source_branches':len(final),'distinct_target_projections':len({r['payload']['model']['target_projection_hash'] for r in final if not v012 or r['id'] not in meta_ids}),
        'checked_family_complete':family_complete,'universal_source_interpretation':False,
        'scientific_status':'CONDITIONAL_RECONSTRUCTION','external_execution_grant':False})


def export(controller, project, case_id, after_record_id, byte_offset, limit, max_bytes):
    case=controller.journal.case(project,case_id)
    source_id=case['payload']['problem'].get('artifact_snapshot_id')
    if source_id is None:raise ValueError('ARTIFACT_CASE_REQUIRED')
    context=resolve(controller.service.store,project,source_id)
    kinds=('artifact_checkpoint','artifact_result','artifact_plan','artifact_revision','artifact_worker_attempt',
        'artifact_semantic_call','automation_step','automation_control')
    if case['payload']['problem'].get('artifact_interpretation') == 'meaning014':
        kinds += ('artifact_baseline_A0','artifact_baseline_check','artifact_interpretation_commit','artifact_discriminator','artifact_source_adjudication','artifact_interpretation_revision')
    inputs=[controller.service.store.get(project,i) for i in case['payload']['source_record_ids']]
    values=[context.record,case,*inputs,*controller.journal.rows(kinds,project,case_id=case_id,after_id=after_record_id,limit=limit+1)]
    values=sorted({r['id']:r for r in values if r['id']>after_record_id}.values(),key=lambda r:r['id'])
    fragments=[];used=0;cursor=after_record_id;offset=byte_offset;more=bool(values)
    source_is_current=current_source(controller,context)
    for row in values:
        data=json.dumps({k:v for k,v in row.items() if k!='payload'},sort_keys=True,ensure_ascii=True,separators=(',',':'))
        if offset<0 or offset>=len(data) and offset!=0:raise ValueError('INVALID_EXPORT_BYTE_OFFSET')
        take=min(len(data)-offset,max_bytes-used-1500)
        if take<=0:break
        binding=row['payload'].get('coordinator_binding',row['payload'].get('state',{}).get('coordinator_binding'))
        current=source_is_current and (binding is None or binding==controller.binding)
        if row['kind']=='artifact_result':current=certificate_current(controller,project,row)
        def fragment(width, row=row, current=current, data=data, offset=offset):
            meta = row['kind'] == 'artifact_result' and row['payload']['model'].get('target_model') == 'NOT_APPLICABLE'
            extra = {'meta_contract_current': current, 'certificate_kind': 'SOURCE_META_TRANSPORT', 'target_model': 'NOT_APPLICABLE'} if meta else {}
            return {**extra, 'record_id':row['id'],'kind':row['kind'],'entry_hash':row['entry_hash'],'json_ascii':data[offset:offset+width],
                'byte_offset':offset,'total_bytes':len(data),'source_version_current':source_is_current,
                'record_integrity_valid':True,'certificate_current':(False if meta else current) if row['kind'] in {'artifact_result','artifact_checkpoint','artifact_plan'} else None}
        while take and len(canonical(fragment(take)).encode())>max_bytes-used-1500:take//=2
        if not take:break
        value=fragment(take);fragments.append(value)
        used+=len(canonical(value).encode())+1;offset+=take
        if offset<len(data):break
        cursor=row['id'];offset=0
        if len(fragments)>=limit:break
    if values:more=cursor<values[-1]['id'] or offset>0
    return {'case_id':case_id,'fragments':fragments,'more':more,'next_after_record_id':cursor,'next_byte_offset':offset,
        'encoding':'ASCII_CANONICAL_RECORD_JSON_FRAGMENTS','reassembly':'Concatenate by record_id/byte_offset; parse row, Store.decode verifies entry_hash.',
        'byte_bound_scope':'UTF8_CANONICAL_EXPORT_PAYLOAD_EXCLUDES_JSONRPC_ENVELOPE',
        'proof_status':'unverified','execution_permission':{'allowed':False}}


def certificate_current(controller, project: str, row: dict) -> bool:
    """A persisted JSON object alone is never a semantic certificate.

    The current source, controller, compiled descriptor and executed checker
    checkpoint must agree. This guards the legacy DAV export path as well as
    the artifact-specific read API.
    """
    if row['kind']!='artifact_result' or row['project']!=project:return False
    p=row['payload'];ctx=resolve(controller.service.store,project,p['source_context']['snapshot_id'])
    if not current_source(controller,ctx) or p['coordinator_binding']!=controller.binding or p['source_context']!=ctx.public():return False
    from semantic_repair.compiler import compile_model
    m=compile_model(p['premises'],p['binding'],profile='typed008/1',context=ctx)
    if m!=p['model']:return False
    check=controller.service.store.get(project,p['checker_checkpoint_id'])
    if check['kind']!='artifact_checkpoint' or check['payload']['action']!='artifact_check':return False
    if any(check['payload'][k]!=p[k] for k in ('case_id','generation','coordinator_binding','source_context')):return False
    actual={k:v for k,v in check['payload']['result'].items() if k!='isolation'}
    checked = actual['analysis']['all_operations_independently_replayed'] is True
    if m.get('target_model') == 'NOT_APPLICABLE':
        checked = actual['analysis'].get('meta_transport_checked') is True and bool(actual['analysis'].get('source_meta_obligations'))
    return p['check']==actual and checked


def report(controller,project,case_id,max_bytes=60000):
    case=controller.journal.case(project,case_id)
    if case['payload']['problem']['kind']!='artifact_reconstruction':raise ValueError('ARTIFACT_CASE_REQUIRED')
    state=controller.journal.steps(project,case_id)[-1]['payload'];result=state['result']
    lines=['# Условная модель текстового артефакта',f"Состояние: {state['status']}; итог: {result.get('outcome','вычисление продолжается')}."]
    if case['payload']['problem'].get('artifact_interpretation') == 'meaning014':
        from .semantic014 import readable
        lines = readable(controller,project,case_id) + ['',*lines]
    if case['payload']['problem'].get('artifact_interpretation') == 'meaning014':
        for ident in result.get('artifact_result_ids',[]):
            product=controller.service.store.get(project,ident)['payload'];model=product['model'];analysis=product['check']['analysis']
            lines.append('Условный формальный продукт '+str(ident)+': '+model.get('target_model','UNKNOWN')+'; source truth не доказана.')
            for t in analysis.get('source_transition_analysis',{}).get('full_state_cycles',[]):
                lines.append('Реально проверенная модельная петля: '+str(len(t['steps']))+' fired steps; physical execution UNKNOWN.')
        lines.append('Полные source claims, потери, finite receipts и старые counterexamples доступны через view=export. B/B+ — основной workflow; C экспериментален.')
        text='\n'.join(lines);raw=text.encode();allowance=max(512,max_bytes-len(canonical(result).encode())-2000);complete=len(raw)<=allowance
        if not complete:text=raw[:allowance].decode('utf-8',errors='ignore')+'\nОтчёт сокращён; полная A0 сохранена в append-only export.'
        return {'case_id':case_id,'status':state['status'],'result':result,'report_ru':text,'report_complete':complete,
            'proof_status':'unverified','execution_permission':{'allowed':False}}
    context=resolve(controller.service.store,project,case['payload']['problem']['artifact_snapshot_id'])
    spans={s['id']:s for w in packets(context)[0] for s in w['spans']}
    for retained in result.get('source_reading_refs', []):
        view = controller.service.store.get(project, retained['checkpoint_id'])['payload']['result']
        lines += ['', 'SOURCE_SUPPORT: сохранён адресованный частичный source-граф HYPOTHESIS.',
            'MODEL_DERIVATION: target-модель не построена; сертификат и разрешение отсутствуют.']
        for reading in view['source_proposals']['readings']:
            if reading['id'] not in retained['reading_ids']:
                continue
            lines.append('Source reading ' + reading['id'] + ': ' + canonical(reading))
    for ident in result.get('artifact_result_ids',[]):
        row=controller.service.store.get(project,ident)['payload'];m=row['model'];a=row['check']['analysis']
        lines+=['',f"Модель {ident}: {m['observer']['kind']}; binding {canonical(row['binding']['assignments'])}.",
            f"Область: {a['full_state_count']} конечных маркировок; source interpretation HYPOTHESIS."]
        if a.get('conditional_observer_inference') is not None:
            from semantic_repair.report013 import readable
            lines.extend(readable(a['conditional_observer_inference']))
        if m['observer']['kind'] == 'SOURCE_TRANSITION':
            general = a['source_transition_analysis']
            lines += ['Математически построено: условная конечная модель; это MODEL_DERIVATION.',
                'SOURCE_SUPPORT: адресованная интерпретация HYPOTHESIS, даже после независимого source critic.',
                'Экспертная литературная оценка: отдельно; данный checker её не устанавливает.',
                'Наблюдатель O: ' + m['observer']['criterion'] + '; признаки ' + canonical(m['observer']['projection_features']),
                'Область C: ' + canonical(general['reachable_states']) + '; T(C) ⊆ C = ' + str(general['T_C_subset_C']) + '.',
                'Замкнутость этой C не доказывает отсутствие выхода во всех физических состояниях.']
            for comparison in general['observation_comparisons']:
                lines.append('Исходное отношение ' + comparison['relation_kind'] + ', полярность ' + comparison['polarity']
                    + ', critic ' + comparison['critic_status'] + ': full state equality=' + str(comparison['full_state_equal'])
                    + ', sequence equality=' + str(comparison['sequence_equal']) + ', set equality=' + str(comparison['set_equal'])
                    + ', Equivalent_O=' + str(comparison['Equivalent_O']) + '; source equality не подтверждено.')
            lines.append('Отрицательные/конфликтующие основания: ' + canonical(m['observer']['source_review_flags']))
            lines.append('Предписание, возможный переход и фактическое исполнение не отождествляются; performance UNKNOWN.')
        if m['observer']['kind'] == 'SOURCE_SEMANTICS012':
            lines += ['SOURCE_SUPPORT: S сообщает H; H остаётся интерпретацией, SOURCE_VERIFIED=false.',
                'MODEL_DERIVATION: ' + ('NOT_APPLICABLE для исполняемой сети; отдельно проверены условные observer013 отношения.' if a.get('conditional_observer_inference') is not None and m['target_model'] == 'NOT_APPLICABLE' else 'NOT_APPLICABLE; проверен только META_TRANSPORT.' if m['target_model'] == 'NOT_APPLICABLE' else 'условная конечная сеть, после freeze выбрано Q.'),
                'Целевая сеть: ' + m['target_model'] + '; математическая проверка не доказывает источник.',
                'Наблюдатели и unknown masks: ' + canonical(m['observer']['observers']),
                'Сравнения: ' + canonical(a['observer_comparisons']),
                'Source/meta obligations: ' + canonical(a['source_meta_obligations']),
                'Loss ledger: ' + canonical(row['check']['loss_ledger']),
                'Свидетельства трасс: ' + canonical(a.get('source_transition_analysis', {})),
                'Фактическое исполнение в мире: UNKNOWN; внешнего разрешения нет.']
        for p in row['premises']:
            lines.append('Исходное чтение: '+p['realization']['label'])
            for ref in p['source_refs']:lines.append(ref+': '+spans[ref]['text'])
        for g in m['guards']:lines.append('Условие '+g['id']+': '+g['text']+'; адреса '+', '.join(g['source_refs']))
        for r in m.get('spec', {}).get('reaction_network', {}).get('reactions', []):
            lines.append(f"{r['id']}: {' + '.join(r['reactants'])} → {' + '.join(r['products'])}")
        for t in a['traces'][:4]:
            lines.append(f"Трасса {t['trace_id']}: "+' → '.join(str(x) for x in [t['initial_state'],*[s['after'] for s in t['steps']]])+f"; все шаги fired={t['all_steps_fired']}.")
            lines.append('Наблюдение: '+canonical(t.get('final_observation', {'scope': 'named observers exported separately'})))
    for loss in result.get('losses', [])[:20]:
        lines.append('Оставшийся разрыв: ' + canonical(loss))
    lines+=['','Не выполненная физика: роли сети не идентифицируют вещества. Предписание не означает исполнение; UNKNOWN не означает отрицание. Source support не следует из target proved.']
    text='\n'.join(lines);raw=text.encode();allowance=max(512,max_bytes-len(canonical(result).encode())-2000)
    complete=len(raw)<=allowance
    if not complete:text=raw[:allowance].decode('utf-8',errors='ignore')+'\nОтчёт сокращён по byte budget; полные объекты доступны через view=export.'
    return {'case_id':case_id,'status':state['status'],'result':result,'report_ru':text,'report_complete':complete,
        'proof_status':'unverified','execution_permission':{'allowed':False}}
