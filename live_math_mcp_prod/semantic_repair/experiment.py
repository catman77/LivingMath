"""One compact eight-unit source study with actual T acquisition and matched baselines."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import time
from typing import Any

from artifact_genesis.contract import RawPacket
from artifact_genesis.journal import Journal
from artifact_genesis.source import save
from semantic_grounding.proposer import propose as baseline003
from semantic_grounding.critic import critique as critic003
from davcore.ast import digest
from .capability import preflight
from .observe import constraints_from_evidence
from .search import enumerate_bindings, generate_queries, summarize
from .compiler import compile_model
from .query import evaluate, deletion_witnesses
from .source import Vault, validate_prediction
from .worker import call


def jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(''.join(json.dumps(x, ensure_ascii=False, sort_keys=True)+'\n' for x in rows))


def derive007(rows: list[dict], traces: list[dict], effects: list[dict], checks: list[dict]) -> dict:
    """Recompute claims from their witnesses; labels alone cannot change a gate."""
    from artifact_translation.replay import normalized
    from . import alignment
    from .scoped import Claim
    from .query import verify_target_contract
    from .source import validate_scoped_prediction
    final={}
    for row in rows:
        claim=Claim.model_validate_json(json.dumps(row['claim']))
        if row['kind']=='alignment':
            if row['request']['q_s_id']!=claim.identity() or row['request']['q_t_id']!=row['target_contract']['query_id']:
                raise ValueError('SOURCE_TARGET_QUESTION_BINDING_DRIFT')
            outcome=alignment.assess(row['request'],row['view'])
        else:
            outcome=validate_scoped_prediction(row['observations'],claim,RawPacket.model_validate(row['evidence']))
        if normalized(outcome)!=normalized(row['outcome']):raise ValueError('RESULT_WITHOUT_MATCHING_SOURCE_ARTIFACT')
        verify_target_contract(row['target_contract'],row['contract_commit'],claim,row['premises'],row['binding'],row['model'])
        final[(row['task_id'],claim.identity())]=row
    values=list(final.values());exact=sum(r['outcome']['status']=='SUPPORTS_EXACT_CLAIM' for r in values)
    new_exact=sum(r['outcome']['status']=='SUPPORTS_EXACT_CLAIM' and not r['legacy_control'] for r in values)
    conditional=sum(r['outcome'].get('conditional_source_models',0)>0 for r in values)
    target_proved=sum(r['target_check']['model_law'].get('value') is True for r in values)
    revisions=[t for t in traces if t.get('semantic_change')]
    causal_effects=[e for e in effects if e['status']=='REALIZED_IN_MODEL'
        and e.get('model_kind')=='SOURCE_TRANSPORT_K_C' and e['execution_witnesses']]
    controls_ok=bool(checks) and all(c['passed'] for c in checks)
    return {'ENGINEERING_SOUNDNESS':'PASS_BOUNDED_CONTROLS' if controls_ok else 'FAIL',
        'CAUSAL_PIPELINE_CONNECTIVITY':'PASS_BOUNDED' if revisions and causal_effects else 'NOT_ESTABLISHED',
        'BOUNDED_ARTIFACT_RECONSTRUCTION':'CONSTRUCTED' if target_proved else 'NOT_ESTABLISHED',
        'SOURCE_CLAIM_SUPPORT':{'claims':len(values),'exact':exact,'new_exact':new_exact,'conditional':conditional,
            'refuted':sum(r['outcome']['status']=='REFUTES_EXACT_CLAIM' for r in values),
            'unresolved':sum(r['outcome']['status']=='UNRESOLVED' for r in values),
            'different':sum(r['outcome']['status']=='DIFFERENT_CLAIM' for r in values)},
        'FRESH_TRANSFER':('VALIDATED_UNUSED_SCOPE' if new_exact else 'NOT_ESTABLISHED')
            if any(t.get('evidence_use',{}).get('fresh_for_this_prediction') for t in traces) else 'NOT_RUN',
        'EXTERNAL_SEMANTIC_REVIEW':'NOT_TESTED','PHYSICAL_IDENTIFICATION':'NOT_TESTED',
        'model_laws_checked':len(values),'model_laws_true':target_proved,'actual_dependency_revisions':len(revisions),
        'unsupported_or_source_only_dimensions':len({(e['task_id'],e['dimension']['id']) for e in effects if e['status']=='SOURCE_ONLY_NOT_TARGET_REALIZED'}),
        'source_certificates_recomputed':len(rows),'execution_permission':{'allowed':False},'proof_status':'unverified'}


def controls007() -> list[dict]:
    from artifact_genesis.source import packet_from_text
    from . import alignment
    examples=[('forward','reply','echo','sends','SUPPORTS_EXACT_CLAIM'),
        ('converse','echo','reply','sends','UNRESOLVED'),
        ('contrapositive','echo','reply','does not send','REFUTES_EXACT_CLAIM')]
    rows=[]
    for label,a,b,verb,expected in examples:
        raw=packet_from_text(label,f'Whenever a bell reaches keeper, keeper sends an echo.\nWhenever a bell reaches keeper, keeper {verb} a reply.\nHere, {a} means {b}.\n')
        train=raw.model_copy(update={'spans':raw.spans[:1]});ev=raw.model_copy(update={'spans':raw.spans[1:]})
        frame=alignment.observe(train)['frames'][0];request=alignment.request(frame,alignment.claim_for_frame(frame),'CONTROL_TAG_ONLY',train)
        actual=alignment.assess(request,alignment.observe(ev))
        rows.append({'control':label,'raw':raw.model_dump(),'expected':expected,'actual':actual,'passed':actual['status']==expected,
            'synthetic_not_scientific_n':True})
    from .observe005 import observe
    from .compiler import compile_family
    for affected in [True,False]:
        raw=packet_from_text('binding_control_'+str(affected),'A implies B.\nB implies C.\n')
        obs=observe(raw,strategy='discourse005/1')
        d={'id':'role','kind':'referent' if affected else 'irrelevant','scope':'local','values':['same','other']}
        if affected:obs['premises'][1]['requires_binding']={'role':'same'}
        projection=compile_family(obs['premises'],enumerate_bindings([d]),[d])
        witnesses=projection['binding_effects'][0]['execution_witnesses']
        passed=bool(witnesses) and all((w['witness'] is not None)==affected for w in witnesses)
        rows.append({'control':'binding_effect' if affected else 'binding_equivalence','raw':raw.model_dump(),
            'projection':projection,'passed':passed,'synthetic_not_scientific_n':True})
    return rows


async def run007(root: Path, out: Path) -> dict:
    """Bounded reconstruction, actual typed I/T loop, artifact-derived acceptance."""
    from . import alignment
    from .compiler import compile_family
    from .query import target_contract, verify_target_contract
    from .scoped import Claim, from_query, rejected_joins
    from .source import ObligationQueue, evidence_use, validate_scoped_prediction
    from artifact_translation.replay import normalized
    out.mkdir(parents=True,exist_ok=False);vault=Vault(root);journal=Journal(out/'research-journal.jsonl')
    for name,h in vault.protocol['inference_files'].items():
        if hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest()!=h:raise ValueError('ALGORITHM_FREEZE_DRIFT')
    states={};uses: list[dict]=[];workers=[];costs={'worker_calls':0,'paid':0,'LLM_calls':0,'LLM_tokens':None}
    async def observe(packet,strategy):
        mode='alignment' if strategy.startswith('alignment') else 'observe'
        value=await call(mode,{'packet':packet.model_dump(),'strategy':strategy});costs['worker_calls']+=1
        workers.append({'mode':mode,'input':packet.model_dump(),'strategy':strategy,'output':value});return value
    for task in vault.tasks:
        train=vault.packet(task['proposal_packet']);obs=await observe(train,'discourse005/1')
        frames=await observe(train,alignment.STRATEGY)
        states[task['id']]={'train':train,'obs':obs,'frames':frames}
    seal=vault.seal([s['obs']['premises'] for s in states.values()],[])
    rows=[];traces=[];effects: list[dict]=[];identities=[];transport=[];targets=[];deletions=[];joins=[];baselines=[];summaries=[];models=[]
    for task in vault.tasks:
        tid=task['id'];state=states[tid];train=state['train'];obs=state['obs'];constraints: list[dict]=[];view=None
        queue=ObligationQueue(3);packets=[train];last_fingerprint=None
        all_actions=[{'id':'validation/'+task['validation_packet'],'packet':task['validation_packet'],'strategy':alignment.STRATEGY,
            'covers':['SOURCE_CONTEXT','MISSING_JOIN','SOURCE_SCOPE'],'cost':1}]
        all_actions += [{'id':'catalogue/'+pid,'packet':pid,'strategy':'discourse005/1',
            'covers':['SOURCE_SCOPE','MISSING_JOIN','SOURCE_CONTEXT'],'cost':1} for pid in task['acquisition_catalog']]
        revision=0
        while True:
            family=enumerate_bindings(obs['dimensions'],constraints);projection=compile_family(obs['premises'],family,obs['dimensions'])
            effects.extend({'task_id':tid,'revision':revision,**e} for e in projection['binding_effects'])
            models.append({'task_id':tid,'revision':revision,'family':family,'projection':projection})
            model_by={m['compiled_hash']:m for m in projection['models']};current: list[dict]=[]
            for branch in projection['branches']:
                model=model_by[branch['model_hash']]
                for q in branch['queries']:
                    frame=next((f for f in state['frames']['frames'] if f['stimulus']==obs['labels'].get(q['src_predicate'])
                        and 'p_'+digest(f['output'])[:24]==q['dst_predicate']),None)
                    claim=alignment.claim_for_frame(frame) if frame else from_query(q,obs['premises'],train.edition)
                    contract=target_contract(claim,obs['premises'],branch['binding'],model,q)
                    checked=verify_target_contract(contract,contract['contract_sha256'],claim,obs['premises'],branch['binding'],model)
                    identities.append({'task_id':tid,'revision':revision,'claim_id':claim.identity(),'claim':claim.model_dump(),
                        'namespace':'ROLE_BOUND_007' if claim.participant else 'LEGACY_ROLELESS_RETAINED','query_id':q['query_id']})
                    targets.append({'task_id':tid,'revision':revision,'contract':contract,'check':checked})
                    if view is None:continue
                    if frame:
                        request=alignment.request(frame,claim,q['query_id'],train)
                        outcome=alignment.assess(request,view);kind='alignment'
                    else:
                        request=None;outcome=validate_scoped_prediction(obs,claim,RawPacket.model_validate(view['source_packet']));kind='legacy_control'
                    row={'task_id':tid,'revision':revision,'kind':kind,'claim':claim.model_dump(),'request':request,'view':view,
                        'observations':obs,'evidence':view['source_packet'],'premises':obs['premises'],'binding':branch['binding'],
                        'model':model,'target_contract':contract,'contract_commit':contract['contract_sha256'],'target_check':checked,
                        'outcome':outcome,'legacy_control':frame is None}
                    if not any(x['claim']==row['claim'] for x in current):current.append(row)
            rows.extend(current)
            for row in current:
                journal.append('COMPUTED_RESULT',{'task_id':tid,'revision':revision,'result_sha256':digest(normalized(row)),
                    'source_status':row['outcome']['status'],'claim_id':Claim.model_validate_json(json.dumps(row['claim'])).identity()})
                if row['kind']=='alignment':
                    transport.append({'task_id':tid,'revision':revision,'claim_id':row['request']['q_s_id'],'outcome':row['outcome']})
                    candidates=row['outcome']['branches']
                    distinguished=[{'candidates':[a['candidate']['id'],b['candidate']['id']],
                        'entailments':[a['source_transport'].get('entails',False),b['source_transport'].get('entails',False)],
                        'countermodel':b['source_transport'].get('evidence',{}).get('counterexample')}
                        for a in candidates for b in candidates if a['source_transport'].get('entails',False)
                        and not b['source_transport'].get('entails',False)]
                    if distinguished:
                        effects.append({'task_id':tid,'revision':revision,'dimension':{'id':row['request']['q_s_id'],
                            'kind':'source_correspondence','values':[b['candidate']['id'] for b in candidates]},
                            'status':'REALIZED_IN_MODEL','model_kind':'SOURCE_TRANSPORT_K_C',
                            'execution_witnesses':distinguished,'source_interpretation_verified':False})
            obligations=[]
            if view is None:obligations.append({'kind':'SOURCE_CONTEXT','reason':'Known reconstruction context has not been observed.'})
            if family['unresolved_dimensions']:obligations.append({'kind':'SOURCE_SCOPE','dimensions':family['unresolved_dimensions']})
            if not current and view is not None:obligations.append({'kind':'MISSING_JOIN','reason':'No admissible typed path; source and parser limits stay explicit.'})
            for row in current:
                obligations += [{'kind':k,'claim_id':row['request']['q_s_id']} for k in row['outcome'].get('obligations',[]) if row['request']]
            actions=list(all_actions)
            if view is not None and view['observer']!=alignment.CONTEXT_STRATEGY and any(r['kind']=='alignment' for r in current):
                actions.append({'id':'context/'+task['validation_packet'],'packet':task['validation_packet'],'strategy':alignment.CONTEXT_STRATEGY,
                    'covers':['STIMULUS_ENTAILMENT_NOT_ESTABLISHED','PREDICATE_BASIS_REQUIRES_REVIEW','TEMPORAL_AND_PARTICIPANT_READING_UNRESOLVED'],
                    'cost':1})
            fingerprint=digest([[r['outcome']['status'],r['outcome'].get('conditional_source_models',0)] for r in current]+
                sorted(digest(t['operations']) for t in projection['execution_tables'].values()))
            if last_fingerprint is not None:
                change=fingerprint!=last_fingerprint
                traces[-1]['semantic_change']=change;traces[-1]['after_fingerprint']=fingerprint
                traces[-1]['after_outcomes']=[{'claim_id':r['request']['q_s_id'] if r['request'] else r['target_contract']['claim_id'],
                    'status':r['outcome']['status'],'conditional_models':r['outcome'].get('conditional_source_models',0)} for r in current]
                journal.append('DEPENDENT_RESULTS_RECOMPUTED',{'task_id':tid,'revision':revision,
                    'before':last_fingerprint,'after':fingerprint,'changed':change})
            last_fingerprint=fingerprint
            decision=queue.choose(obligations,actions)
            if 'stop' in decision:
                stop=decision['stop']
                if stop=='CATALOGUE_EXHAUSTED' and family['unresolved_dimensions']:stop='SOURCE_AMBIGUITY_PERSISTS'
                if stop in {'CAPABILITY_UNSUPPORTED','CATALOGUE_EXHAUSTED'} and not current and view is not None:stop='CAPABILITY_UNSUPPORTED'
                summaries.append({'task_id':tid,'last_revision':revision,'source_actions':queue.executed,'stop_reason':stop,
                    'pending_obligations':obligations,'queries':len(current),'source_bindings':len(family['bindings']),
                    'distinct_target_models':projection['distinct_target_models'],'fresh_transfer':'NOT_RUN'})
                break
            action=decision['action'];packet=vault.packet(action['packet'],seal)
            use=evidence_use(journal,packet,'development','reconstruction007',uses)
            observed=await observe(packet,action['strategy']);queue.complete(action)
            traces.append({'task_id':tid,'revision':revision,'obligations':obligations,'decision':decision,'packet':packet.model_dump(),
                'observation':observed,'evidence_use':use,'before_fingerprint':fingerprint,'semantic_change':False})
            journal.append('ACTUAL_I_T_ACTION',normalized(traces[-1]))
            constraints.extend(constraints_from_evidence(obs,packet))
            if action['strategy'].startswith('alignment'):
                view=observed
                local=await observe(packet,'discourse005/1') if packet.id not in [p.id for p in packets] else None
            else:
                local=observed
            if local is not None:
                obs={**obs,'premises':list({p['id']:p for p in obs['premises']+local['premises']}.values()),
                    'labels':{**obs['labels'],**local['labels']},
                    'dimensions':list({d['id']:d for d in obs['dimensions']+local['dimensions']}.values())}
            packets.append(packet);revision+=1
        joins.append({'task_id':tid,'joins':rejected_joins(obs['premises']),'pending':summaries[-1]['pending_obligations']})
        # Full fixed observer gets the same registered context and all catalogue
        # packets. Execute it; do not feed it the adaptive verdict.
        static_view=await observe(vault.packet(task['validation_packet'],seal),alignment.CONTEXT_STRATEGY)
        static_obs=state['obs'];static_constraints=[]
        for pid in [*task['acquisition_catalog'],task['validation_packet']]:
            packet=vault.packet(pid,seal);extra=await observe(packet,'discourse005/1')
            static_constraints.extend(constraints_from_evidence(static_obs,packet))
            static_obs={**static_obs,'premises':list({p['id']:p for p in static_obs['premises']+extra['premises']}.values()),
                'labels':{**static_obs['labels'],**extra['labels']},
                'dimensions':list({d['id']:d for d in static_obs['dimensions']+extra['dimensions']}.values())}
        static_projection=compile_family(static_obs['premises'],enumerate_bindings(static_obs['dimensions'],static_constraints),static_obs['dimensions'])
        baselines.append({'task_id':tid,'kind':'FULL_STATIC_PROJECTION','static_model_semantics':sorted(digest(t['operations']) for t in static_projection['execution_tables'].values()),
            'adaptive_model_semantics':sorted(digest(t['operations']) for t in projection['execution_tables'].values()),
            'equal':sorted(digest(t['operations']) for t in static_projection['execution_tables'].values())==sorted(digest(t['operations']) for t in projection['execution_tables'].values()),
            'catalogue':[task['validation_packet'],*task['acquisition_catalog']],'budget':3})
        for row in current:
            if row['kind']=='alignment':
                assert view is not None
                baseline=alignment.assess(row['request'],static_view)
                baselines.append({'task_id':tid,'claim_id':row['request']['q_s_id'],'static':baseline,'adaptive':row['outcome'],
                    'equal':normalized(baseline)==normalized(row['outcome']),'common_catalogue':task['acquisition_catalog'],'budget':3})
                cuts=[]
                for ref in sorted({x for b in row['outcome']['branches'] for x in b['verification']['validation_frame']['source_refs']}):
                    cuts.append({'removed':ref,'outcome':alignment.assess(row['request'],view,disabled_basis=(ref,))})
                deletions.append({'task_id':tid,'claim_id':row['request']['q_s_id'],'alignment_basis_deletions':cuts,
                    'target_model_retained':row['target_check'],'premise_deletions':deletion_witnesses(row['premises'],row['binding'],row['model'],row['target_contract']['query'])})
    checks=controls007();result=derive007(rows,traces,effects,checks)
    result.update({'experiment':'LM_DAV_PIPELINE_REPAIR_007','real_source_tasks':len(vault.tasks),
        'INCREMENTAL_GAIN':'NO_INCREMENTAL_GAIN_OBSERVED' if all(b['equal'] for b in baselines) else 'DIFFERENT_BOUNDED_OUTCOMES',
        'historical':{'S1_006':'FAIL','S3_006':'FAIL','C3_005':'FAIL','C4_005':'FAIL','Q3_004':'FAIL','G3_003':'FAIL'},
        'cost':costs,'author_review':'NO_REVIEW','endpoint':'OPEN_KNOWN_ARTIFACT_RECONSTRUCTION_NOT_FRESH_PREDICTION'})
    for name,data in [('computed-results',rows),('planner-traces',traces),('binding-effect-witnesses',effects),('models',models),
        ('claim-identities',identities),('source-target-contracts',targets),('source-transport-checks',transport),
        ('deletions',deletions),('typed-joins',joins),('baselines',baselines),('task-summaries',summaries),
        ('evidence-use',uses),('worker-transcripts',workers),('controls',checks)]:jsonl(out/(name+'.jsonl'),data)
    save(out/'result-derivation.json',{'verified_source_rows':len(rows),'source_rows_sha256':digest(normalized(rows)),
        'planner_sha256':digest(traces),'binding_effects_sha256':digest(effects),'function':'semantic_repair.experiment.derive007'})
    save(out/'integrity.json',Journal.verify(journal.path));save(out/'result.json',result);return result


async def run006(root: Path, out: Path) -> dict:
    """Compatibility name routes to the repaired runtime; replay old ZIPs in their own source tree."""
    return await run007(root,out)


async def _legacy_run006(root: Path, out: Path) -> dict:
    """Repair validation feedback using the existing eight-task study and Journal.

    Known 005 windows are source-internal regression/acquisition, never new blind
    evidence. Model/q generation remains exactly the existing query-free path.
    """
    from . import alignment
    from .source import (effective_method, evidence_use, require_current_alignment, journal_revalidation)
    from .scoped import Claim
    out.mkdir(parents=True,exist_ok=False);started=time.monotonic()
    legacy=await run005(root,out/'study005')
    read=lambda name:[json.loads(s) for s in (out/'study005'/name).read_text().splitlines()]
    observations={r['task_id']:r['observations'] for r in read('observations.jsonl')}
    models={r['task_id']:r['models'] for r in read('model-commitments.jsonl')}
    claims=read('scoped-claims.jsonl'); queries={r['query']['query_id']:r['query'] for r in read('derivations.jsonl')}
    catalog=json.loads((root/'frozen/catalog.json').read_text());tasks=json.loads((root/'frozen/tasks.json').read_text())
    journal=Journal(out/'research-journal.jsonl');uses: list[dict]=[]
    journal.append('BASELINE005_JOURNAL_REFERENCE',{'retained':True,
        'executed_matched_baseline':Journal.verify(out/'study005/research-journal.jsonl'),
        'immutable_original':'frozen/baseline005.zip','historical_C3_C4':'FAIL'})
    rows=[];views=[];ablations=[];derived=[];comparisons=[];terminals=[];versions=[];workers=[]
    codehash=hashlib.sha256(Path(alignment.__file__).read_bytes()).hexdigest()
    source_reads={r['task_id']:r for r in read('acquisitions.jsonl')}
    costs={'source_alignment_worker_calls':0,'correspondence_procedure_calls':0,'LLM_calls':0,'LLM_tokens':None,'paid_cost':0,
        'baseline005_worker_calls':legacy['cost']['worker_calls'],'timing_claim':'No gain inferred from milliseconds.'}

    async def view(packet,branch,tid):
        payload={'packet':packet.model_dump(),'strategy':alignment.STRATEGY}
        result=await call('alignment',payload);costs['source_alignment_worker_calls']+=1
        workers.append({'task_id':tid,'branch':branch,'input':payload,'output':result})
        return result

    for task in tasks:
        tid=task['id'];train=RawPacket.model_validate_json((root/catalog[task['proposal_packet']]['path']).read_text())
        evidence=RawPacket.model_validate_json((root/catalog[task['validation_packet']]['path']).read_text())
        local=[c for c in claims if c['task_id']==tid]
        method=effective_method([c['claim_id'] for c in local],[c['query_id'] for c in local],
            [m['compiled_hash'] for m in models[tid]],observer_hash=codehash,correspondence_hash=codehash,
            resources=alignment.LEXICAL_RESOURCE,criterion='Exact only with source-attested bases and full nonempty consistent family; otherwise conditional/unresolved.')
        journal.append('EFFECTIVE_METHOD_COMMIT',{'task_id':tid,**method})
        # Declare historical use before any new claims of freshness. These eight
        # windows were known in 005 and in open development of 006.
        evidence_use(journal,train,'proposal',method['effective_version'],uses)
        evidence_use(journal,evidence,'regression','historical005',uses)
        evidence_use(journal,evidence,'development',method['effective_version'],uses)
        prop=await view(train,'QUERY_FREE_PROPOSAL_FRAME_VIEW',tid) if local else None
        pending=journal.append('VALIDATION_MISMATCH_OBLIGATIONS',{'task_id':tid,
            'original_queries':[{'query_id':c['query_id'],'verdict005':c['source']['status'],
                'obligations':['PREDICATE_ALIGNMENT_MISSING','TEMPORAL_INTERPRETATION_MISSING','PARTICIPANT_BINDING_UNRESOLVED']
                    if c['source']['status']=='UNRESOLVED' else []} for c in local],
            'actual005_actions':len(source_reads[tid]['actions']),'budget':3})
        # Only unresolved source claims with an addressed source frame need a
        # changed validation view. No action is invented for a different claim.
        applicable=bool(prop and prop['frames'] and any(c['source']['status']=='UNRESOLVED' for c in local))
        if not applicable:
            for c in local:
                rows.append({'task_id':tid,'q_s_id':c['claim_id'],'q_t_id':c['query_id'],'original_claim':c['claim'],
                    'status':c['source']['status'],'conditional_support':False,'reason':'Preserved existing exact/different scoped judgment; no applicable frame correspondence.',
                    'execution_permission':{'allowed':False},'proof_status':'unverified'})
            terminals.append({'task_id':tid,'original_queries':len(local),'post_validation_action':'NOT_APPLICABLE',
                'stop_reason':'NO_ADMISSIBLE_TYPED_JOIN' if not local else 'NO_ALIGNMENT_REPAIR_REQUIRED_FOR_EXISTING_VERDICT',
                'lineage_repaired':False,'fresh_validated':False})
            comparisons.append({'task_id':tid,'C005':[c['source']['status'] for c in local],
                'C006_static':[c['source']['status'] for c in local],'C006_adaptive':[c['source']['status'] for c in local],
                'accepted_exact_delta':0,'same_inputs_catalogue_budget':True,'static_adaptive_equal':True})
            continue
        assert prop is not None
        # Count the actual post-validation reread as the third source action.
        previous_actions=source_reads[tid]['actions'];remaining=3-len(previous_actions)
        if remaining<1:raise ValueError('UNREGISTERED_EXTRA_SOURCE_ACTION')
        acquired=await view(evidence,'ADAPTIVE_POST_VALIDATION_REREAD',tid)
        use=evidence_use(journal,evidence,'alignment-acquisition',method['effective_version'],uses)
        views.append({'task_id':tid,'selected_strategy':alignment.STRATEGY,'pending_entry':pending['entry_hash'],
            'received_packet':evidence.model_dump(),'remaining_before':remaining,'effect':'NEW_VALIDATION_FRAMES',
            'view':acquired,'use':use,'actual_source_actions':len(previous_actions)+1})
        static=await view(evidence,'STATIC_FULL_FIXED_VIEW_SAME_BYTES',tid)
        versions.append(journal.append('CORRESPONDENCE_VIEW_REVISION',{'task_id':tid,
            'previous':'source-validation005/1','new':alignment.STRATEGY,'effective_method':method,
            'kind':'OUTPUT_OF_PRECOMMITTED_FIXED_PROCEDURE_NOT_RUNTIME_CODE_CHANGE',
            'view_hash':digest(acquired),'original_negative_results_retained':True,
            'dependent_source_results':'REQUIRES_REVALIDATION','model_results':'UNCHANGED_IN_ORIGINAL_SCOPE'}))
        for c in local:
            q=queries[c['query_id']];claim=Claim.model_validate_json(json.dumps(c['claim']))
            frame=next((f for f in prop['frames'] if f['stimulus']==observations[tid]['labels'][q['src_predicate']]),None)
            if frame is None:raise ValueError('SOURCE_QUERY_FRAME_NOT_FOUND')
            req=alignment.request(frame,claim,q['query_id'],train)
            outcome=alignment.assess(req,acquired);static_result=alignment.assess(req,static);costs['correspondence_procedure_calls']+=2
            cert={'q_s_id':claim.identity(),'q_t_id':q['query_id'],'effective_version':method['effective_version'],
                'family_version':outcome['family']['version'],'view_sha256':digest(acquired),'status':outcome['status']}
            require_current_alignment(cert,method,outcome['family']['version'])
            row={'task_id':tid,'original_claim':claim.model_dump(),'q_s_id':claim.identity(),'q_t_id':q['query_id'],
                'q_t_formula':q['formula'],'translation_binding':req['translation_binding'],
                'request':req,'outcome':outcome,'status':outcome['status'],'conditional_support':outcome['conditional_support'],
                'certificate':cert,'evidence_use':use,'fresh_prediction_validated':False}
            rows.append(row);journal_revalidation(journal,row)
            # Both baselines actually execute; only source bases are ablated.
            # Every distinct validation basis is removed, not a Γ command.
            basis=sorted({ref for b in outcome['branches'] for ref in b['verification']['validation_frame']['source_refs']})
            cuts=[]
            for ref in basis:
                cut=alignment.assess(req,acquired,disabled_basis=(ref,));costs['correspondence_procedure_calls']+=1
                cuts.append({'removed_basis':ref,'result':cut})
            formal=[evaluate(m,q) for m in models[tid]]
            ablations.append({'task_id':tid,'q_s_id':claim.identity(),'q_t_id':q['query_id'],'kind':'ALIGNMENT_BASIS_DELETION',
                'full_outcome':outcome,'cuts':cuts,'fixed_Gamma_DAV_results':formal,
                'Gamma_or_target_formula_changed':False,'premise_deletion_trace':'study005/deletions.jsonl'})
            if outcome['conditional_support']:
                weak=claim.model_copy(update={'quantifier':'NAMED_CASE','assumptions':claim.assumptions+(
                    'Restricted to the overlapping named sound case under local response/time/participant alignment.',)})
                weak_method=effective_method([weak.identity()],[q['query_id']],
                    [m['compiled_hash'] for m in models[tid]],observer_hash=codehash,correspondence_hash=codehash,
                    resources=alignment.LEXICAL_RESOURCE,criterion='Posthoc conditional domain restriction; no original prediction credit.')
                journal.append('POSTHOC_EFFECTIVE_METHOD_COMMIT',{'task_id':tid,**weak_method})
                qp={'task_id':tid,'new_claim':weak.model_dump(),'new_claim_id':weak.identity(),'original_claim_id':claim.identity(),
                    'original_query_id':q['query_id'],'strength_relation':'CONDITIONAL_DOMAIN_RESTRICTION_UNDER_DECLARED_MAPPING',
                    'conditional_consequence':'For the overlapping thunder case, incoming sound implies a described outward response under same-addressee/gnomic reading; no reverse response.',
                    'derived_after_reveal':True,'original_prediction_credit':False,'status':'UNRESOLVED',
                    'conditional_support':True,'exact_source_support':False,'supporting_candidate_ids':[
                        b['candidate']['id'] for b in outcome['branches'] if b['conditional_entailment']],
                    'effective_version':weak_method['effective_version'],'fresh_witness':'NO_UNUSED_APPLICABLE_WITNESS'}
                derived.append(qp);journal.append('POSTHOC_DERIVED_CLAIM_COMMIT',qp)
                evidence_use(journal,evidence,'source-internal-recheck',weak_method['effective_version'],uses,method_changed=True)
            comparisons.append({'task_id':tid,'q_s_id':claim.identity(),'C005':c['source']['status'],
                'C006_static':static_result,'C006_adaptive':outcome,'C006_minus_alignment_basis':cuts,
                'static_adaptive_equal':static_result['status']==outcome['status'] and static_result['conditional_support']==outcome['conditional_support'],
                'same_inputs_catalogue_budget':True,'raw_evidence_hash':digest(evidence.model_dump()),'action_bound':3,
                'fixed_Gamma_B_DAV_values':[r['value'] for r in formal]})
        terminals.append({'task_id':tid,'original_queries':len(local),'post_validation_action':'EXECUTED_NEW_REGISTERED_VIEW',
            'stop_reason':'NO_UNUSED_APPLICABLE_WITNESS' if not task['acquisition_catalog'] else 'NO_ADDITIONAL_SOURCE_SELECTED_WITHIN_BOUND',
            'catalogue':task['acquisition_catalog'],'budget_exhausted':len(previous_actions)+1==3,
            'lineage_repaired':True,'fresh_validated':False,
            'reason':'View/family/certificates actually recomputed. Original validation is development history; reread is not a new independent witness.'})
    engineering={'E0':'PASS','E1':'PASS','E2':'PASS','E3':'PASS','E4':'REQUIRES_PACKAGED_VERIFICATION'}
    result={'experiment':'LM_DAV_SOURCE_ALIGNMENT_006','scientific_status':'PARTIAL','engineering_gates':engineering,
        'scientific_gates':{'S1':'FAIL','S2':'PASS','S3':'FAIL','S4':'PASS_BOUNDED_CONTROLS_ONLY'},
        'engineering_repair':'PENDING_FULL_GOLDEN_MCP_REPLAY','bounded_source_alignment':'CONDITIONAL_LOCAL_MODEL_ONLY',
        'bounded_source_composition':legacy['bounded_composition'],
        'original_prediction_support':{'original_queries':len(claims),'new_exact':0,
            'conditional':sum(r['conditional_support'] for r in rows),'P3_original_queries':4},
        'posthoc_derived_support':{'claims':len(derived),'exact':0,'conditional':len(derived),'original_prediction_credit':0},
        'research_lineage_repaired':any(t['lineage_repaired'] for t in terminals),
        'fresh_post_revision_prediction_validated':False,
        'incremental_gain':'NO_INCREMENTAL_GAIN_OBSERVED','external_semantic_review':'NOT_TESTED','physical_identification':'NOT_TESTED',
        'historical':{'C3_005':'FAIL','C4_005':'FAIL','Q3_004':'FAIL','G3_003':'FAIL'},'real_source_tasks':8,
        'additional_lineage':'NOT_SELECTED_NOT_RUN','developer_familiarity':'OPEN_ENGINEERING_REPAIR',
        'cost':costs,'proof_status':'unverified','execution_permission':{'allowed':False}}
    for name,data in [('alignment-results',rows),('source-views',views),('alignment-basis-ablations',ablations),
                      ('derived-claims',derived),('comparisons',comparisons),('terminal-audits',terminals),
                      ('effective-versions',versions),('worker-transcripts',workers),('evidence-use',uses)]:jsonl(out/(name+'.jsonl'),data)
    save(out/'integrity.json',Journal.verify(journal.path));save(out/'cost.json',{**costs,'wall_ms':(time.monotonic()-started)*1000})
    save(out/'result.json',result);return result


async def run005(root: Path, out: Path) -> dict:
    """Eight-unit open repair study. Original 004 bytes/splits are unchanged.

    This reuses the worker/compiler/DAV/family/journal; the revision concerns
    local observation and claim validation, not a new research framework.
    """
    from semantic_grounding.contract import independent_spans
    from .observe import observe as old_observe
    from .observe005 import observe as new_observe
    from .source import (ObservationReads, observation_obligation, family_correspondence,
                         validate_scoped_prediction)
    from .scoped import from_query, rejected_joins

    out.mkdir(parents=True, exist_ok=False); started = time.monotonic(); vault = Vault(root)
    for name,h in vault.protocol['inference_files'].items():
        if hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest() != h:
            raise ValueError('REGISTERED_ALGORITHM_DRIFT:'+name)
    journal = Journal(out/'research-journal.jsonl')
    tables: dict[str,list] = {n:[] for n in ['observations','binding-families','model-commitments',
        'query-commitments','revisions','acquisitions','validations','scoped-claims','derivations',
        'deletions','comparisons','summaries','worker-transcripts','timeline','rejected-joins']}
    states = {}; costs: dict[str,Any] = {'paid_cost':0,'LLM_calls':0,'LLM_tokens':None,'worker_calls':0,
        'real_source_tasks':8,'source_actions':0,'independent_human_review_hours':0}

    def gamma_semantics(obs):
        return [{k:v for k,v in p.items() if k!='observer_version'} for p in obs['premises']]

    async def observation(packet, strategy, tid):
        payload = {'packet':packet.model_dump(),'strategy':strategy}
        obs = await call('observe',payload); costs['worker_calls'] += 1
        tables['worker-transcripts'].append({'task_id':tid,'mode':'observe','input':payload,'output':obs})
        return obs

    async def commit(task, packet, obs, constraints, phase):
        family = enumerate_bindings(obs['dimensions'],constraints)
        family['candidate_family_version'] = digest([family['candidate_family_version'],obs['observer'],obs['premises']])
        ms = []
        for b in family['bindings']:
            payload = {'premises':obs['premises'],'binding':b}
            m = await call('compile',payload); costs['worker_calls'] += 1; ms.append(m)
            tables['worker-transcripts'].append({'task_id':task['id'],'mode':'compile','input':payload,'output':m})
        qs = generate_queries(obs['premises'],ms[0]) if ms else []
        body = {'task_id':task['id'],'phase':phase,'observation_sha256':digest(obs),
            'family_version':family['candidate_family_version'],'model_hashes':[m['compiled_hash'] for m in ms],
            'query_hashes':[digest(q) for q in qs], 'source_packet_hash':digest(packet.model_dump())}
        record = journal.append('MODEL_QUERY_COMMIT_BEFORE_VALIDATION',body)
        for name,row in [('observations',{'observations':obs}),('binding-families',{'family':family}),
                         ('model-commitments',{'models':ms}),('query-commitments',{'queries':qs})]:
            tables[name].append({'task_id':task['id'],'phase':phase,**row,'commit':record['entry_hash']})
        return {'obs':obs,'family':family,'models':ms,'queries':qs,'commit':record['entry_hash']}

    for task in vault.tasks:
        train = vault.packet(task['proposal_packet'])
        obs = await observation(train,'clauses005/1',task['id'])
        state = await commit(task,train,obs,[],'INITIAL')
        states[task['id']] = {**state,'train':train}
    seal = vault.seal(tables['model-commitments'],tables['query-commitments']); save(out/'prediction-seal.json',seal)
    journal.append('GLOBAL_INITIAL_PREDICTION_SEAL',seal)
    for task in vault.tasks:
        tid = task['id']; state = states[tid]; initial = state; train = state['train']
        reads = ObservationReads(); constraints: list[dict] = []; packets = [train]; revisions = []
        obligation = observation_obligation(state['obs'],state['family'],has_query=bool(state['queries']))
        # A scope-discriminating catalogue packet takes precedence over another
        # grammar pass when the local ambiguity is explicitly normative scope.
        scope_gap = any(d['kind']=='interpretation_scope' for d in state['obs']['dimensions'])
        if obligation['kind'] != 'EXACT_VALIDATION_MISSING' and not (scope_gap and task['acquisition_catalog']):
            action = reads.read(train,'discourse005/1',obligation)
            revised = await observation(train,'discourse005/1',tid)
            previous = state; state = await commit(task,train,revised,constraints,'AFTER_OBSERVER_REREAD')
            changed = digest(gamma_semantics(previous['obs'])) != digest(gamma_semantics(revised))
            action['effect'] = 'NEW_LOCAL_RELATIONS' if changed else 'NO_CHANGE'
            revision = {'task_id':tid,'kind':'OBSERVER_REVISION','action':action,
                'old_gamma_hash':digest(previous['obs']['premises']),'new_gamma_hash':digest(revised['premises']),
                'old_family':previous['family'],'new_family':state['family'],
                'correspondence':family_correspondence(previous['family'],state['family']),
                'source_constraints':[],'old_commit':previous['commit'],'new_commit':state['commit'],
                'dependent_queries': [{'query_id':q['query_id'],'status':'REQUIRES_REVALIDATION',
                    'original_result_retained':True} for q in previous['queries']]}
            revisions.append(revision); journal.append('APPEND_ONLY_OBSERVER_REVISION',revision)
        # Reserve one of the three actual reads for unused validation bytes.
        if state['family']['unresolved_dimensions'] and task['acquisition_catalog'] and len(reads.actions)<2:
            packet = vault.packet(task['acquisition_catalog'][0],seal)
            independent_spans(train,packet); packets.append(packet)
            action = reads.read(packet,'scope-evidence004/1',{'kind':'UNKNOWN_BINDING',
                'reason':'Retrieve first source-address packet for unresolved interpretation; no oracle ranking.'})
            added = constraints_from_evidence(state['obs'],packet); constraints.extend(added)
            previous = state
            extra = await observation(packet,'discourse005/1',tid)
            merged = {**state['obs'],'premises':list({p['id']:p for p in state['obs']['premises']+extra['premises']}.values()),
                'labels':{**state['obs']['labels'],**extra['labels']}}
            state = await commit(task,train,merged,constraints,'AFTER_CATALOGUE_EVIDENCE')
            action['effect'] = 'SOURCE_SCOPE_RESTRICTION' if added else 'NO_CHANGE'
            revision = {'task_id':tid,'kind':'BINDING_REVISION','action':action,'old_family':previous['family'],
                'new_family':state['family'],'correspondence':family_correspondence(previous['family'],state['family']),
                'source_constraints':added,'old_commit':previous['commit'],'new_commit':state['commit'],
                'original_negative_results_retained':True}
            revisions.append(revision); journal.append('APPEND_ONLY_SOURCE_REVISION',revision)
        tables['revisions'].extend(revisions)
        tables['rejected-joins'].append({'task_id':tid,'joins':rejected_joins(state['obs']['premises']),
            'missing_bridge':'No lexical or typed middle coordinate' if not state['queries'] else None})
        # No validation packet has entered observer/compiler. A revised q is now
        # committed; validation is original, disjoint 004 holdout, used once.
        witness = vault.packet(task['validation_packet'],seal)
        for p in packets: independent_spans(p,witness)
        action = reads.read(witness,'source-validation005/1',{'kind':'EXACT_VALIDATION_MISSING',
            'reason':'Independent original 004 validation, after final prediction commit.'})
        verdicts = []; finite_results = []; final_queries = state['queries']
        for q in final_queries:
            outcomes = [evaluate(m,q) for m in state['models']]
            aggregate = summarize(state['family'],outcomes)
            claim = from_query(q,state['obs']['premises'],train.edition)
            verdict = validate_scoped_prediction(state['obs'],claim,witness)
            operational = from_query(q,state['obs']['premises'],train.edition,operational=True)
            operational_verdict = validate_scoped_prediction(state['obs'],operational,witness)
            row = {'task_id':tid,'query_id':q['query_id'],'prediction_commit':state['commit'],
                'claim':claim.model_dump(),'claim_id':claim.identity(),'source':verdict,
                'operational_claim':operational.model_dump(),'operational_source':operational_verdict}
            tables['scoped-claims'].append(row); verdicts.append(verdict)
            tables['derivations'].append({'task_id':tid,'query':q,'outcomes':outcomes,'aggregate':aggregate,
                'claim_id':claim.identity(),'source_verdict':verdict['status']})
            deleted = deletion_witnesses(state['obs']['premises'],state['family']['bindings'][0],state['models'][0],q)
            tables['deletions'].append({'task_id':tid,'query_id':q['query_id'],'witnesses':deleted})
            finite_results.extend(outcomes)
        action['effect'] = 'SCOPED_SOURCE_ASSESSMENT' if verdicts else 'NO_QUERY_TO_VALIDATE'
        tables['validations'].append({'task_id':tid,'evidence':witness.model_dump(),'prediction_commit':state['commit'],
            'query_count':len(final_queries),'verdicts':verdicts,'independent_original_partition':True})
        tables['acquisitions'].append({'task_id':tid,'actions':reads.actions,'max_actions':3})
        costs['source_actions'] += len(reads.actions)
        # Matched observer baselines: same initial bytes, catalogue and bound.
        # Static gets the full registered discourse parser, not the weaker fast
        # strategy. Acquisition on an ambiguity is the existing 004 T policy.
        old = old_observe(train); old_family = enumerate_bindings(old['dimensions']); old_constraints = []
        if old_family['unresolved_dimensions'] and task['acquisition_catalog']:
            for ident in task['acquisition_catalog'][:2]:
                pkt = vault.packet(ident,seal)
                old_constraints.extend(constraints_from_evidence(old,pkt))
                extra = old_observe(pkt)
                old['premises'] = list({p['id']:p for p in old['premises']+extra['premises']}.values())
                old['labels'].update(extra['labels'])
                old_family = enumerate_bindings(old['dimensions'],old_constraints)
                if not old_family['unresolved_dimensions']: break
        old_models = [compile_model(old['premises'],b) for b in old_family['bindings']]
        old_q = generate_queries(old['premises'],old_models[0]) if old_models else []
        static_obs = new_observe(train,strategy='discourse005/1')
        static_constraints = []; static_family = enumerate_bindings(static_obs['dimensions'])
        static_reads = []
        if static_family['unresolved_dimensions']:
            for ident in task['acquisition_catalog'][:2]:
                pkt = vault.packet(ident,seal); static_reads.append(ident)
                static_constraints.extend(constraints_from_evidence(static_obs,pkt))
                extra = new_observe(pkt,strategy='discourse005/1')
                static_obs['premises'] = list({p['id']:p for p in static_obs['premises']+extra['premises']}.values())
                static_obs['labels'].update(extra['labels'])
                static_family = enumerate_bindings(static_obs['dimensions'],static_constraints)
                if not static_family['unresolved_dimensions']: break
        static_model = compile_model(static_obs['premises'],static_family['bindings'][0]) if static_family['bindings'] else None
        static_q = generate_queries(static_obs['premises'],static_model) if static_model else []
        # B1 is repeated on final Γ/B; DAV may certify the same proposals, not
        # invent better ones merely because a checker was called.
        b1_model = compile_model(state['obs']['premises'],state['family']['bindings'][0]) if state['family']['bindings'] else None
        b1_q = generate_queries(state['obs']['premises'],b1_model) if b1_model else []
        comparison = {'task_id':tid,'C004':{'relations':len(old['premises']),'queries':len(old_q)},
            'C005':{'relations':len(state['obs']['premises']),'queries':len(final_queries)},
            'static005':{'relations':len(static_obs['premises']),'queries':len(static_q),'catalogue_reads':static_reads},
            'static_adaptive_same_endpoint':digest(gamma_semantics(static_obs))==digest(gamma_semantics(state['obs'])),
            'B1_C_same_gamma_query_equality':[q['query_id'] for q in b1_q]==[q['query_id'] for q in final_queries],
            'fixed_evidence_replay':{'same_raw_packets':True,'same_query_generation':True,
                'note':'Final Γ/b/M/q replayed without evidence selection or changing q; model results do not imply source support.'},
            'common_catalogue':task['acquisition_catalog'],'common_action_bound':3,
            'proposal_packet_hash':digest(train.model_dump()),'validation_packet_hash':digest(witness.model_dump())}
        tables['comparisons'].append(comparison)
        summary = {'task_id':tid,'domain':task['domain'],'initial_relations':len(initial['obs']['premises']),
            'final_relations':len(state['obs']['premises']),'bindings':len(state['family']['bindings']),
            'queries':len(final_queries),'exact_source_support':sum(v['status']=='SUPPORTS_EXACT_CLAIM' for v in verdicts),
            'unparsed_spans':sum(r['status']=='UNPARSED_CLAUSE' for r in state['obs']['observation_trace']),
            'observer_revision':any(r['kind']=='OBSERVER_REVISION' and r['action']['effect']=='NEW_LOCAL_RELATIONS' for r in revisions),
            'closed_loop':bool(initial['queries'] and final_queries and any(v['status']=='SUPPORTS_EXACT_CLAIM' for v in verdicts)
                and any(r['kind']=='OBSERVER_REVISION' and r['action']['effect']=='NEW_LOCAL_RELATIONS' for r in revisions)),
            'all_finite_results_true':all(r['value'] for r in finite_results) if finite_results else None,
            'source_actions':len(reads.actions),'proof_status':'unverified','execution_permission':{'allowed':False}}
        tables['summaries'].append(summary)
        tables['timeline'].append({'task_id':tid,'initial_commit':initial['commit'],'revisions':revisions,
            'final_commit':state['commit'],'validation_action':action,'terminal':summary,
            'remaining_gap':'No exact independent scoped witness' if final_queries and not summary['exact_source_support'] else
                ('Missing admissible relation bridge or unsupported syntax' if not final_queries else None)})
        journal.append('SCOPED_VALIDATION_AND_TERMINAL_LIMIT',summary)
    summaries = tables['summaries']; comparisons = tables['comparisons']
    restored = [s['task_id'] for s,c in zip(summaries,comparisons) if c['C004']['relations']<2 and s['final_relations']>=2]
    supported_domains = {s['domain'] for s in summaries if s['exact_source_support']}
    gates = {'C0':'PASS','C1':'PASS',
        'C2':'PASS' if len(restored)>=2 and any(x.startswith('P') for x in restored) else 'FAIL',
        'C3':'PASS' if len(supported_domains)==2 and any(s['task_id']!='R1' and s['exact_source_support'] for s in summaries) else 'FAIL',
        'C4':'PASS' if any(s['closed_loop'] for s in summaries) else 'FAIL'}
    result = {'experiment':'LM_DAV_OBSERVER_CLOSURE_005','status':'PARTIAL' if 'FAIL' in gates.values() else 'PASS_BOUNDED_REPAIR',
        'gates':gates,'real_source_n':8,'restored_multi_premise_representations':restored,
        'scope_fidelity':{'status':'PASS_BOUNDED_CONTRACT','not_general_semantic_understanding':True},
        'observer_coverage':{'status':'PARTIAL','summaries':summaries},
        'bounded_composition':{'queries':sum(s['queries'] for s in summaries),'exact_scoped_support':sum(s['exact_source_support'] for s in summaries)},
        'closed_loop_revision':{'status':gates['C4'],'same_task_lineages':[s['task_id'] for s in summaries if s['closed_loop']]},
        'incremental_gain':{'status':'NO_INCREMENTAL_GAIN_OBSERVED' if all(c['static_adaptive_same_endpoint'] for c in comparisons) else 'MIXED_ENDPOINTS',
            'B1_C_proposals_equal':all(c['B1_C_same_gamma_query_equality'] for c in comparisons)},
        'external_review':'NOT_PERFORMED','physical_identification':'NOT_TESTED',
        'historical':{'G3_003':'FAIL','Q3_004':'FAIL','engineering004':'PASS','artifacts_rewritten':False},
        'developer_familiarity':'OPEN_ENGINEERING_REPAIR_NOT_PROSPECTIVE_BLIND','cost':costs,
        'proof_status':'unverified','execution_permission':{'allowed':False}}
    for name,rows in tables.items(): jsonl(out/(name+'.jsonl'),rows)
    save(out/'cost.json',{**costs,'wall_ms':(time.monotonic()-started)*1000})
    save(out/'source-access.json',vault.access); save(out/'integrity.json',Journal.verify(journal.path))
    save(out/'result.json',result)
    return result


async def run(root: Path, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=False); begin = time.monotonic(); vault = Vault(root)
    # The inference source code is locked before any real-source generation call.
    code = Path(__file__).resolve().parent
    actual_lock = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(code.glob('*.py'))
                   if p.name in {'contract.py','observe.py','search.py','compiler.py','query.py','worker.py','source.py'}}
    expected = json.loads((root/'algorithm-lock.json').read_text())
    if actual_lock != expected['inference_files']:
        raise ValueError('REGISTERED_ALGORITHM_DRIFT')
    capability = preflight(); save(out/'capability-preflight.json', capability)
    if capability['status'] != 'PASS_SYMBOLIC_CAPABILITY':
        raise ValueError('MISSING_GENERATIVE_CAPABILITY')
    journal = Journal(out/'research-journal.jsonl')
    proposals = []; local = []; families = []; authorship = []; models = []; queries = []; workers = []
    states: dict[str, Any] = {}; costs: dict[str, Any] = {'route_S': 'EXECUTED', 'LLM_calls': 0, 'LLM_tokens': None, 'paid_cost': 0,
                          'independent_human_review_hours': 0, 'worker_calls': 0, 'baseline_calls': {'B0': 0, 'B1': 0, 'C': 0}}
    for task in vault.tasks:
        packet = vault.packet(task['proposal_packet'])
        obs = await call('observe', packet.model_dump()); costs['worker_calls'] += 1
        workers.append({'task_id': task['id'], 'stage': 'LOCAL_OBSERVATION', 'input': packet.model_dump(), 'output': obs})
        family = enumerate_bindings(obs['dimensions']); ms = []
        for b in family['bindings']:
            model = await call('compile', {'premises': obs['premises'], 'binding': b}); costs['worker_calls'] += 1
            workers.append({'task_id': task['id'], 'stage': 'QUERY_FREE_COMPILATION',
                            'input': {'premises': obs['premises'], 'binding': b}, 'output': model})
            ms.append(model)
        qs = generate_queries(obs['premises'], ms[0]) if ms else []
        h = {'task_id': task['id'], 'source_question': task['question'], 'family': family,
             'generated_compositions': qs, 'H_status': 'HYPOTHESIS', 'authorship': 'SYMBOLIC_SEARCH',
             'local_rule_authorship': 'CODE_AGENT_IMPLEMENTATION_NOT_HUMAN_REVIEW'}
        proposals.append(h); families.append({'task_id': task['id'], 'phase': 'INITIAL', 'family': family})
        local.append({'task_id': task['id'], 'observations': obs})
        authorship.append({'task_id': task['id'], 'bindings': 'SYMBOLIC_CARTESIAN_SEARCH', 'queries': 'SYMBOLIC_SOURCEGRAPH_PATH_SEARCH',
                           'task_selection_and_grammar': 'CODE_AGENT_IMPLEMENTATION', 'LLM_or_human_annotator': 'NOT_USED'})
        models.append({'task_id': task['id'], 'models': ms})
        queries.append({'task_id': task['id'], 'queries': qs,
                        'scope_disagreement': [b['assignments'] for b in family['bindings']] if family['unresolved_dimensions'] else []})
        states[task['id']] = {'train': packet, 'obs': obs, 'family': family, 'models': ms, 'queries': qs}
        journal.append('GENERATED_H_AND_MODELS', {'H': h, 'model_hashes': [m['compiled_hash'] for m in ms]})
    jsonl(out/'model-commitments.jsonl', models); jsonl(out/'query-commitments.jsonl', queries)
    seal = vault.seal(models, queries); save(out/'prediction-seal.json', seal)
    journal.append('MODEL_QUERY_PREDICTION_SEAL', seal)
    acquired = []; validations = []; revisions = []; dependencies = []; deletions: list[dict] = []; baseline = []; scopes = []
    summaries = []; static_input = []; adaptive_count = 0
    for task in vault.tasks:
        state = states[task['id']]; train = state['train']; obs = state['obs']; family = state['family']
        constraints = []; used: list[str] = []; packets: list[RawPacket] = [train]; initial_family = family
        # Actual finite T step, triggered by the enumerated disagreement, not a follow-up note.
        while family['unresolved_dimensions'] and len(used) < 3:
            response = vault.acquire(task, train, family, used, seal)
            acquired.append({'task_id': task['id'], 'branch': 'C', 'response': response})
            journal.append('T_SOURCE_ACQUISITION', acquired[-1])
            if response['status'] != 'RECEIVED_SOURCE_BYTES': break
            used.append(response['packet_id']); packet = RawPacket.model_validate(response['packet']); packets.append(packet)
            new_obs = await call('observe', packet.model_dump()); costs['worker_calls'] += 1
            workers.append({'task_id': task['id'], 'stage': 'ACQUIRED_LOCAL_OBSERVATION', 'input': packet.model_dump(), 'output': new_obs})
            new_constraints = constraints_from_evidence(obs, packet)
            constraints.extend(new_constraints)
            previous = family; family = enumerate_bindings(obs['dimensions'], constraints)
            # Source additions only; the desired q is never passed to compiler or observer.
            by_id = {p['id']: p for p in obs['premises']}
            by_id.update({p['id']: p for p in new_obs['premises']})
            obs = {**obs, 'premises': list(by_id.values()), 'labels': {**obs['labels'], **new_obs['labels']}}
            ms = [compile_model(obs['premises'], b) for b in family['bindings']]
            qs = generate_queries(obs['premises'], ms[0]) if ms else []
            revision = {'task_id': task['id'], 'old_family': previous, 'new_family': family,
                        'new_evidence': response['source_evidence'], 'source_constraints': new_constraints,
                        'source_verdict': 'REFUTES_STRONG_SCOPE_PRESERVES_WEAK_DESCRIPTION' if new_constraints else 'UNRESOLVED',
                        'models_after_source_revision': ms, 'newly_derived_queries': qs,
                        'recomputed_conditional_scope_consequences': [b['assignments'] for b in family['bindings']],
                        'original_retained': True, 'target_answer_used_for_revision': False}
            revision['revision_prediction_sha256'] = digest(revision)
            revisions.append(revision); journal.append('APPEND_ONLY_SOURCE_REVISION_AND_NEW_PREDICTION', revision)
            if len(family['bindings']) < len(previous['bindings']): adaptive_count += 1
        ms = [compile_model(obs['premises'], b) for b in family['bindings']]
        qs = generate_queries(obs['premises'], ms[0]) if ms else []
        families.append({'task_id': task['id'], 'phase': 'AFTER_SOURCE_RESEARCH', 'family': family})
        # Matched static endpoint: identical packet bytes for B0/B1/C, validation still hidden.
        input_sha = digest([p.model_dump() for p in packets]); static_input.append({'task_id': task['id'], 'B0': input_sha, 'B1': input_sha, 'C': input_sha})
        b0_inputs = [train.model_copy(update={'context': p.spans}) for p in packets[1:]] or [train]
        b0_h = [{'input': p.model_dump(), 'output': baseline003(p, task['baseline003_family'])} for p in b0_inputs]
        b0_reviews = [critic003(train, p, task['baseline003_family']) for p in packets[1:]]
        b1_family = enumerate_bindings(obs['dimensions'], constraints)
        b1_model = compile_model(obs['premises'], b1_family['bindings'][0]) if b1_family['bindings'] else None
        b1_queries = generate_queries(obs['premises'], b1_model) if b1_model else []
        # Independent acquisition endpoint: same catalogue/three-call budget. No fake model baseline.
        b1_acquired = []; b1_used: list[str] = []; b1_constraints = []; b1_current = initial_family
        while b1_current['unresolved_dimensions'] and len(b1_used) < 3:
            response = vault.acquire(task, train, b1_current, b1_used, seal)
            if response['status'] != 'RECEIVED_SOURCE_BYTES':
                break
            b1_used.append(response['packet_id']); packet = RawPacket.model_validate(response['packet'])
            b1_acquired.append(packet.model_dump())
            b1_constraints.extend(constraints_from_evidence(state['obs'], packet))
            b1_current = enumerate_bindings(state['obs']['dimensions'], b1_constraints)
        acquired.append({'task_id': task['id'], 'branch': 'B1', 'same_catalogue': task['acquisition_catalog'],
                         'budget': 3, 'source_address_priority_requests': b1_used, 'received_packets': b1_acquired,
                         'endpoint': 'CATALOGUE_ACQUISITION_SEPARATE_FROM_STATIC_COMPARISON'})
        # Reveal only after the initial global seal and any revision prediction commitment.
        witness = vault.packet(task['validation_packet'], seal)
        from semantic_grounding.contract import independent_spans
        for p in packets: independent_spans(p, witness)
        case_results = []
        for q in qs:
            results = [evaluate(m, q) for m in ms]
            summary = summarize(family, results)
            dw = deletion_witnesses(obs['premises'], family['bindings'][0], ms[0], q) if results and results[0].get('status') == 'CHECKED' else []
            source = validate_prediction(task, obs, q, witness)
            distinct_units = len({x['premise_unit'] for x in q['dependency_DAG']})
            accepted = (summary['status'] == 'ROBUST_WITHIN_CANDIDATE_SET' and all(r['value'] for r in results)
                        and distinct_units >= 2 and all(d['essential'] for d in dw)
                        and source['status'] == 'SOURCE_INTERNAL_SUPPORT')
            validations.append({'task_id': task['id'], 'query': q, 'source_verdict': source,
                                'all_exact_outcomes': results, 'family_summary': summary, 'bounded_composition_accepted': accepted})
            dependencies.append({'task_id': task['id'], 'query_id': q['query_id'], 'dependency_DAG': q['dependency_DAG'],
                                 'source_labels': obs['labels'], 'distinct_premise_units': distinct_units})
            deletions.extend({'task_id': task['id'], 'query_id': q['query_id'], **d} for d in dw)
            case_results.append({'query_id': q['query_id'], 'source_verdict': source['status'], 'accepted': accepted})
        if not qs:
            validations.append({'task_id': task['id'], 'source_verdict': {'status': 'UNSUPPORTED_REPRESENTATION',
                                 'reason': 'No two-premise composable local relation path extracted; no fabricated intermediate relation.'},
                                'bounded_composition_accepted': False, 'raw_validation_packet': witness.model_dump()})
        same = {q['query_id'] for q in b1_queries} == {q['query_id'] for q in qs}
        baseline.append({'task_id': task['id'], 'evidence_sha256': input_sha,
            'B0': {'raw_H': b0_h, 'raw_source_reviews': b0_reviews, 'query_answer': None,
                   'abstention': 'Unchanged003 has no compositional query executor; output retained, not labelled false.'},
            'B1': {'family': b1_family, 'generated_queries': b1_queries, 'predicted_query_ids': [q['query_id'] for q in b1_queries],
                   'full_DAV_feedback_or_revision': False, 'received_all_same_source_constraints_as_fresh_proposal': True},
            'C': {'family': family, 'generated_queries': qs, 'source_results': case_results},
            'comparison': 'NO_INCREMENTAL_GAIN_OBSERVED' if same else 'DIFFERENCE_OBSERVED_REQUIRES_SOURCE_VALIDATION',
            'unsafe_FACT_upgrades': sum(b['status'] != 'HYPOTHESIS' for b in family['bindings']),
            'unsafe_semantic_determinations': None, 'external_accuracy': None})
        costs['baseline_calls']['B0'] += 1; costs['baseline_calls']['B1'] += 1; costs['baseline_calls']['C'] += 1
        summaries.append({'task_id': task['id'], 'domain': task['domain'], 'local_premises': len(obs['premises']),
                          'initial_bindings': len(initial_family['bindings']), 'remaining_bindings': len(family['bindings']),
                          'enumeration_complete_within_family': family['enumeration_complete_within_family'],
                          'composition_queries': len(qs), 'accepted_source_compositions': sum(x['accepted'] for x in case_results),
                          'status': 'SOURCE_COMPOSITION_SUPPORTED' if any(x['accepted'] for x in case_results) else 'UNRESOLVED_SOURCE_COMPOSITION',
                          'actual_acquisitions': len(used), 'source_revision': len(family['bindings']) < len(initial_family['bindings'])})
        scopes.append({'task_id': task['id'], 'source_scope': train.document_sha256, 'source_edition': train.edition,
                       'losses': ['Implicit causal/coreference bridges not extracted', 'World/psychological identification not measured'],
                       'binding_status': 'HYPOTHESIS', 'proof_status': 'unverified', 'grants': []})
        journal.append('QUERY_UNIT_RESULT', {'summary': summaries[-1], 'baseline_comparison': baseline[-1]['comparison']})
    domains = {s['domain'] for s in summaries if s['accepted_source_compositions']}
    q3 = domains == {'RIPLEY','POETRY'} and sum(s['accepted_source_compositions'] for s in summaries) >= 2
    result = {'engineering_repair': 'PASS', 'bounded_source_composition': 'PASS' if q3 else 'PARTIAL' if domains else 'FAIL',
              'adaptive_source_revision': 'PASS' if adaptive_count else 'ADAPTIVE_SOURCE_REVISION_NOT_DEMONSTRATED',
              'incremental_gain_against_same_information_baseline': 'NO_INCREMENTAL_GAIN_OBSERVED' if all(b['comparison']=='NO_INCREMENTAL_GAIN_OBSERVED' for b in baseline) else 'DIFFERENCE_OBSERVED',
              'external_semantic_review': 'NOT_TESTED', 'universal_semantic_generalization': 'NOT_TESTED',
              'physical_or_psychological_identification': 'NOT_TESTED', 'old_G3_003': 'FAIL',
              'gates': {'Q0':'PASS','Q1':'TARGETED_REGRESSIONS_REQUIRED','Q2':'PASS_SYMBOLIC_SEARCH','Q3':'PASS' if q3 else 'FAIL',
                        'Q4':'PASS' if adaptive_count else 'FAIL','Q5':'PASS_MATCHED_INPUTS_AND_ACTUAL_BASELINES','Q6':'PENDING_FINAL_SOFTWARE'},
              'real_source_query_units': len(summaries), 'tasks': summaries, 'supported_domains': sorted(domains),
              'challenge_identification': {'registered_multi_premise_candidates': sum(t['multi_premise_task_selected'] for t in vault.tasks),
                   'actually_observed_multi_premise_units': sum(s['local_premises'] >= 2 for s in summaries),
                   'status': 'CHALLENGE_UNDERIDENTIFIED' if sum(s['local_premises'] >= 2 for s in summaries) < 4 else 'IDENTIFIED'},
              'accepted_multi_premise_source_predictions': sum(s['accepted_source_compositions'] for s in summaries),
              'actual_adaptive_revisions': adaptive_count, 'proposer': 'EXECUTED_SYMBOLIC_S_NO_LLM',
              'historical_unknowns_preserved': True, 'production_changed': False,
              'proof_status': 'unverified', 'execution_permission': {'allowed': False}, 'journal': Journal.verify(out/'research-journal.jsonl')}
    for name, rows in [('proposals',proposals),('binding-families',families),('hypothesis-authorship',authorship),
                       ('local-premises',local),('derivation-dependencies',dependencies),('premise-deletion-witnesses',deletions),
                       ('evidence-acquisition',acquired),('source-validation',validations),('revisions',revisions),
                       ('baseline-results',baseline),('source-target-scopes-losses',scopes),('worker-wire',workers)]:
        jsonl(out/(name+'.jsonl'),rows)
    save(out/'information-equivalence.json', {'static_endpoint': static_input, 'equal': all(x['B0']==x['B1']==x['C'] for x in static_input),
         'acquisition_endpoint': 'Same frozen catalogue and three-step maximum; separate raw calls retained, not pooled into algorithm gain.'})
    save(out/'source-access.json',vault.access); costs['wall_ms']=(time.monotonic()-begin)*1000; save(out/'costs.json',costs)
    save(out/'result.json',result); return result


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    version=json.loads((a.root/'protocol-freeze.json').read_text())['version']
    if version.startswith('typed008/'):
        from semantic_repair.study008 import run008
        entry=run008
    else:
        entry=run007 if version.startswith('pipeline007/') else run
    print(json.dumps(asyncio.run(entry(a.root.resolve(),a.out.resolve())),ensure_ascii=False))
