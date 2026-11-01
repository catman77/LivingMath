"""Bounded typed realization in the existing worker, Vault and I/T queue path."""
import asyncio
import copy
import hashlib
from itertools import combinations
import json
from pathlib import Path
import shutil
import sys
from zipfile import ZipFile

from artifact_genesis.journal import Journal
from artifact_genesis.source import save
from artifact_translation.replay import normalized
from davcore.ast import digest
from .compiler import compile_model
from .source import Vault, ObligationQueue
from .search import enumerate_bindings
from .trace008 import questions, certify, evaluate, study_model, compare, trace, adapter
from .realization import PROFILE, observe_state
from .worker import call


def jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(''.join(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n' for r in rows))


def merge_slices(observations: list[dict]) -> list[dict]:
    """Only presentation cursors share an interface; signed branches stay local."""
    slices=[copy.deepcopy(s) for o in observations for s in o['slices']]
    textual=[s for s in slices if s['kind']=='TEXTUAL_PROGRESSION']
    if textual:
        ps={p['id']:p for s in textual for p in s['premises']}
        joint={**textual[0],'premises':sorted(ps.values(),key=lambda p:p['realization']['source_order'])}
        slices=[s for s in slices if s['kind']!='TEXTUAL_PROGRESSION']+[joint]
    # A new reading of the same packet replaces its typed projection, but old
    # observations, certificates and models remain in earlier artifact rows.
    unique={digest([s['kind'],[p['id'] for p in s['premises']]]):s for s in slices}
    return list(unique.values())


async def run008(root: Path, out: Path) -> dict:
    out.mkdir(parents=True,exist_ok=False);vault=Vault(root);journal=Journal(out/'research-journal.jsonl')
    proto=json.loads((root/'protocol-freeze.json').read_text())
    for name,h in proto['inference_files'].items():
        if hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()!=h:
            raise ValueError('INFERENCE_DRIFT:'+name)
    # Real B0: its original code, not a label attached to the new compiler.
    baseline=out/'immutable007';baseline.mkdir()
    with ZipFile(root/'frozen/baseline007.zip') as z:
        for name in z.namelist():
            if not (baseline/name).resolve().is_relative_to(baseline.resolve()):raise ValueError('UNSAFE_BASELINE_MEMBER')
        z.extractall(baseline)
    old=baseline/'PIPELINE_REPAIR_007'
    process=await asyncio.create_subprocess_exec(sys.executable,'-B','-m','semantic_repair.experiment',
        '--root',str(old/'pipeline_repair007'),'--out',str(out/'B0-unchanged007'),
        stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,cwd=str(old/'live_math_mcp_prod'))
    stdout,stderr=await process.communicate();(out/'B0-run.log').write_bytes(stdout+stderr)
    if process.returncode:raise ValueError('UNCHANGED007_BASELINE_FAILED')
    # Keep all five non-primary cases and original exact source questions on
    # the unchanged legacy path, exercising backward compatibility on new code.
    from .experiment import run007
    legacy_root=out/'legacy-input007'
    shutil.copytree(old/'pipeline_repair007',legacy_root)
    legacy_protocol=json.loads((legacy_root/'protocol-freeze.json').read_text())
    legacy_protocol['version']='pipeline007/compatibility-on-typed008'
    legacy_protocol['inference_files']=proto['inference_files']
    save(legacy_root/'protocol-freeze.json',legacy_protocol)
    legacy=await run007(legacy_root,out/'legacy007-current')
    b0=json.loads((out/'B0-unchanged007/result.json').read_text())
    if normalized(b0)!=normalized(legacy):raise ValueError('LEGACY007_RESULT_DRIFT')
    stores: dict[str,list[dict]]={n:[] for n in ['source-freeze','typed-relations','realization-contracts','formal-models','query-commitments',
        'trace-certificates','source-target-contracts','source-loss-ledger','counterexamples','revision-history',
        'planner-traces','binding-effect-witnesses','baseline-comparison','coverage-by-relation-type','worker-transcripts','costs']}
    costs={'B0':{'source_read_bound':3,'worker_calls':b0['cost']['worker_calls']},
        'B1':{'source_read_bound':4,'source_reads':0,'compiler_calls':0},'C':{'source_read_bound':4,'source_reads':0,'compiler_calls':0}}

    async def read(task,branch,packet,strategy):
        response=await call('observe',{'packet':packet.model_dump(),'strategy':strategy})
        stores['worker-transcripts'].append({'task_id':task['id'],'branch':branch,'mode':'observe',
            'input':{'packet':packet.model_dump(),'strategy':strategy},'output':response})
        costs[branch]['source_reads']+=1
        stores['source-freeze'].append({'task_id':task['id'],'branch':branch,'packet':packet.model_dump(),
            'packet_hash':digest(packet.model_dump()),'strategy':strategy,'role':'KNOWN_SOURCE_DEVELOPMENT'})
        return response

    async def construct(task,branch,revision,observations):
        records=[];projections={}
        for slice_number,s in enumerate(merge_slices(observations)):
            family=enumerate_bindings(s['dimensions'])
            if not family['bindings']:raise ValueError('EMPTY_FAMILY_NO_VACUOUS_SUPPORT')
            if family['truncated']:raise ValueError('FAMILY_BOUND_NO_UNIVERSAL_ROBUSTNESS')
            for binding in family['bindings']:
                payload={'premises':s['premises'],'binding':binding,'profile':PROFILE}
                raw=await call('compile',payload);model={k:v for k,v in raw.items() if k!='isolation'}
                costs[branch]['compiler_calls']+=1
                stores['worker-transcripts'].append({'task_id':task['id'],'branch':branch,'mode':'compile','input':payload,'output':raw})
                base={'task_id':task['id'],'branch':branch,'revision':revision,'slice':slice_number,
                    'binding':binding,'source_refs':sorted({r for p in s['premises'] for r in p['source_refs']})}
                if model['status']=='COMPILED_CONDITIONAL_MODEL':
                    projection=model['target_projection_hash']
                    projections.setdefault(projection,model['compiled_hash'])
                    base.update(target_projection_id=projection,projection_representative_model_hash=projections[projection],
                        family_branch_retained=True)
                stores['typed-relations'].append({**base,'premises':s['premises'],'family_complete':True,'family_empty':False,
                    'source_relation_kind':s['kind'],'dimensions':s['dimensions'],'family':family})
                stores['formal-models'].append({**base,'model':model})
                if model['status']!='COMPILED_CONDITIONAL_MODEL':
                    stores['source-loss-ledger'].append({**base,'losses':model['losses']});continue
                analysis=study_model(model);qs=questions(model)
                # Fixed query-type budget, committed before truth evaluation.
                selected=[q for q in qs if q['kind']=='PERSISTENCE'][:4]
                selected+= [next(q for q in qs if q['kind']==kind) for kind in ('ORDER','ROUND_TRIP_EQUALITY_ONLY') if any(q['kind']==kind for q in qs)]
                stores['query-commitments'].append({**base,'model_hash':model['compiled_hash'],'queries':qs,
                    'evaluated_query_ids':[q['id'] for q in selected],'query_budget':6,'selection':'FIRST_FOUR_PERSISTENCE_THEN_FIRST_TWO_ORDER_ROUNDTRIP'})
                results=[]
                for q in selected:
                    contract=certify(s['premises'],binding,model,q);result=evaluate(s['premises'],binding,model,contract)
                    stores['source-target-contracts'].append({**base,'contract':contract,'result':result});results.append(result)
                record={**base,'model':model,'analysis':analysis,'premises':s['premises'],'results':results}
                records.append(record);stores['trace-certificates'].append({**base,**analysis})
                stores['realization-contracts'].append({**base,'model_hash':model['compiled_hash'],
                    'source_premises_hash':digest(s['premises']),'profile':PROFILE,'role_map':model['role_map'],
                    'guards':model['guards'],'update_interpretation':binding['assignments'],
                    'initial_states':model['initial_states'],'assumptions':model['assumptions'],
                    'scope':'CONDITIONAL_ENCODING_NOT_SOURCE_PROOF','sealed_before_queries':True,
                    'source_observation_hashes':[digest(o) for o in observations]})
                stores['source-loss-ledger'].append({**base,'model_hash':model['compiled_hash'],'losses':model['losses'],
                    'interfaces':model['interface'],'source_status':'HYPOTHESIS_NOT_FACT','fresh':'NOT_RUN'})
        # Compare one-dimension interventions only; equality is scoped to the
        # exact target observer and every state, not a universal source claim.
        for left,right in combinations(records,2):
            if left['slice']!=right['slice']:continue
            aa=left['binding']['assignments'];bb=right['binding']['assignments']
            changed=[k for k in aa if aa[k]!=bb.get(k)]
            if len(changed)!=1:continue
            stores['binding-effect-witnesses'].append({'task_id':task['id'],'branch':branch,'revision':revision,
                'dimension':changed[0],**compare(left['model'],right['model'])})
        journal.append('TYPED_MODELS_FROZEN_AND_CHECKED',{'task_id':task['id'],'branch':branch,'revision':revision,
            'models':[r['model']['compiled_hash'] for r in records], 'outcomes':[r['analysis']['outcome'] for r in records]})
        return records

    final={};initial={};prepared={};proposals={}
    for task in vault.tasks:
        proposal=vault.packet(task['proposal_packet']);proposals[task['id']]=proposal
        for branch in ('B1','C'):
            observation=await read(task,branch,proposal,'typed008/1')
            records=await construct(task,branch,0,[observation])
            prepared[(task['id'],branch)]=(observation,records)
    sealed_models=[r['model'] for _,rs in prepared.values() for r in rs]
    seal=vault.seal(sealed_models,[q for m in sealed_models for q in questions(m)])
    journal.append('IMMUTABLE_INITIAL_MODEL_QUERY_SEAL',seal)
    for task in vault.tasks:
        proposal=proposals[task['id']]
        evidence_ids=list(dict.fromkeys([*task['acquisition_catalog'],task['validation_packet']]))
        actions=[{'id':pid,'packet_id':pid,'strategy':'typed008/1',
            'covers':['UNOBSERVED_CONTEXT','PRESCRIPTION_NOT_OBSERVED','BACK_SIGN_UNKNOWN'],'cost':1} for pid in evidence_ids]
        # A second registered interpretation view is available equally to B1/C.
        # Selection is by current structural mismatch, never desired truth.
        for branch in ('B1','C'):
            observation,records=prepared[(task['id'],branch)]
            observations=[observation];initial[(task['id'],branch)]=records
            local_actions=copy.deepcopy(actions)
            if any(s['kind']=='GUARDED_TRANSFORMATION' for s in observations[0]['slices']):
                local_actions.insert(0,{'id':'middle:'+proposal.id,'packet_id':proposal.id,'strategy':'typed008-middle/1',
                    'covers':['UNBOUND_FORMAL_MIDDLE'],'cost':0})
            queue=ObligationQueue(budget=4);queue.complete({'id':'initial:'+proposal.id})
            revision=0
            choice: dict
            while True:
                obligations=[]
                if any(r['model']['observer']['kind']=='GUARDED_TRANSFORMATION' and r['analysis']['outcome']=='NO_ENABLED_COMPLETE_TRACE' for r in records) and not any(o['observer']=='typed008-middle/1' for o in observations):
                    obligations.append({'kind':'UNBOUND_FORMAL_MIDDLE'})
                if any(r['model']['observer']['kind']=='TEXTUAL_PROGRESSION' and not any(p['realization']['kind']=='PRESCRIPTION' for p in r['premises']) for r in records):
                    obligations.append({'kind':'PRESCRIPTION_NOT_OBSERVED'})
                if any(r['model']['observer']['kind']=='SIGNED_RESPONSE' and all(t['final_observation']['back_status']=='UNKNOWN' for t in r['analysis']['traces']) for r in records):
                    obligations.append({'kind':'BACK_SIGN_UNKNOWN'})
                if any(a['id'] not in queue.used for a in local_actions if not a['id'].startswith('middle:')):
                    obligations.append({'kind':'UNOBSERVED_CONTEXT'})
                if branch=='B1':
                    remaining=[a for a in local_actions if a['id'] not in queue.used]
                    choice={'action':remaining[0],'policy':'FULL_STATIC_CATALOGUE_SOURCE_ORDER'} if remaining and queue.executed<4 else {'stop':'CATALOGUE_EXHAUSTED' if not remaining else 'BUDGET_EXHAUSTED'}
                else:choice=queue.choose(obligations,local_actions)
                if 'action' not in choice:
                    stores['planner-traces'].append({'task_id':task['id'],'branch':branch,'revision':revision,'obligations':obligations,**choice});break
                action=choice['action'];before=records
                packet=proposal if action['packet_id']==proposal.id else vault.packet(action['packet_id'],vault._seal)
                obs=await read(task,branch,packet,action['strategy']);queue.complete(action);revision+=1
                if action['strategy']=='typed008-middle/1':observations[0]=obs
                else:observations.append(obs)
                records=await construct(task,branch,revision,observations)
                prior_out=[r['analysis']['outcome'] for r in before];new_out=[r['analysis']['outcome'] for r in records]
                revision_row={'task_id':task['id'],'branch':branch,'revision':revision,'obligations':obligations,'action':action,
                    'previous_model_hashes':[r['model']['compiled_hash'] for r in before],
                    'new_model_hashes':[r['model']['compiled_hash'] for r in records],
                    'previous_outcomes':prior_out,'new_outcomes':new_out,
                    'executed_effect':prior_out!=new_out,
                    'new_enabled_complete_trace':any(r['analysis']['outcome']=='HAS_ENABLED_TRACE' for r in records) and not any(r['analysis']['outcome']=='HAS_ENABLED_TRACE' for r in before),
                    'new_normative_trace':any(t['final_observation'].get('prescription')=='ATTESTED' for r in records for t in r['analysis']['traces']) and not any(t['final_observation'].get('prescription')=='ATTESTED' for r in before for t in r['analysis']['traces']),
                    'previous_certificates':'RETAINED_IN_ORIGINAL_SCOPE_REAUDIT_REQUIRED',
                    'source_status':'CONDITIONAL_RECONSTRUCTION','query_recomputed':True,'no_desired_verdict_received':True}
                stores['revision-history'].append(revision_row);stores['planner-traces'].append({**revision_row,'selection':choice})
                journal.append('ACTUAL_INTERPRETATION_ATTENTION_REVISION',revision_row)
            final[(task['id'],branch)]=records
        left=sorted(r['model']['compiled_hash'] for r in final[(task['id'],'B1')]);right=sorted(r['model']['compiled_hash'] for r in final[(task['id'],'C')])
        stores['baseline-comparison'].append({'task_id':task['id'],'B0':'ACTUAL_UNCHANGED007',
            'B1_model_hashes':left,'C_model_hashes':right,'same_final_models':left==right,
            'C_minus_B1':'NO_INCREMENTAL_GAIN_OBSERVED' if left==right else 'DIFFERENT_RECONSTRUCTION',
            'B1_C_equal_catalogue':True,'B1_C_source_budget':4,'B0_source_budget':3,
            'B1_minus_B0':'EXECUTABLE_TYPED_PROJECTION' if left else 'LEGACY_SCOPE_RETAINED'})

    # Real, source-bound deletions: retain all coordinates and operation IDs;
    # withdraw an operation without pretending its identity was an event.
    for task in vault.tasks:
        for r in final[(task['id'],'C')]:
            if not any(t['all_steps_fired'] for t in r['analysis']['traces']):continue
            m=r['model'];full=next(t for t in r['analysis']['traces'] if t['all_steps_fired'])
            for p in r['premises']:
                deleted=compile_model(r['premises'],r['binding'],profile=PROFILE,disabled=(p['id'],))
                after=trace(deleted,full['initial_state'],m['premise_ids'])
                stores['counterexamples'].append({'task_id':task['id'],'kind':'SOURCE_UNIT_DELETION','premise_id':p['id'],
                    'source_refs':p['source_refs'],'before':full,'after':after,
                    'distinguished':full['final_state']!=after['final_state'] and not after['all_steps_fired'],
                    'classification':'MODEL_DERIVATION','not_a_discovered_physical_law':True})
            for g in m['guards']:
                without=full['initial_state']&~(1<<g['coordinate'])
                after=trace(m,without,m['premise_ids'])
                stores['counterexamples'].append({'task_id':task['id'],'kind':'GUARD_ABSENT','guard':g,
                    'before':full,'after':after,'distinguished':not after['all_steps_fired'],
                    'classification':'ENCODING_CHECK'})
    for r in stores['typed-relations']:
        stores['coverage-by-relation-type'].append({'task_id':r['task_id'],'branch':r['branch'],'revision':r['revision'],
            'kind':r['source_relation_kind'],'source_refs':r['source_refs'],'premise_ids':[p['id'] for p in r['premises']]})
    # D: compute changes under explicitly invalid semantic mutations; these are
    # countercontrols, never admissible branches or extra successful systems.
    for task in vault.tasks:
        rs=final[(task['id'],'C')]
        for kind in ('GUARDED_TRANSFORMATION','TEXTUAL_PROGRESSION','SIGNED_RESPONSE'):
            r=next((r for r in rs if r['model']['observer']['kind']==kind and any(t['all_steps_fired'] for t in r['analysis']['traces'])),None)
            if r is None:continue
            m=r['model'];t=next(t for t in r['analysis']['traces'] if t['all_steps_fired'])
            if kind=='GUARDED_TRANSFORMATION':
                mutant=copy.deepcopy(m);g=m['guards'][0];sid=mutant['spec']['reaction_network']['species'][g['coordinate']]['id']
                for reaction in mutant['spec']['reaction_network']['reactions']:
                    reaction['reactants'].pop(sid,None);reaction['products'].pop(sid,None)
                witness=next(({'state':s,'source_operation_id':pid,'original':trace(m,s,[pid]),'mutant':trace(mutant,s,[pid])}
                    for s in adapter(m).states() for pid in m['premise_ids']
                    if trace(m,s,[pid])['final_state']!=trace(mutant,s,[pid])['final_state']),None)
                stores['counterexamples'].append({'task_id':task['id'],'kind':'D_GUARD_BASIS_REMOVED','witness':witness,
                    'distinguished':witness is not None,'classification':'ENCODING_CHECK','mutant_is_admissible':False})
            elif kind=='TEXTUAL_PROGRESSION':
                if len(r['premises'])>=2:
                    ps=copy.deepcopy(r['premises']);ps[0],ps[1]=ps[1],ps[0]
                    mutant=compile_model(ps,r['binding'],profile=PROFILE)
                    after=trace(mutant,t['initial_state'],m['premise_ids'])
                    stores['counterexamples'].append({'task_id':task['id'],'kind':'D_SOURCE_OCCURRENCE_PERMUTED',
                        'before':t,'after':after,'distinguished':not after['all_steps_fired'],'classification':'MODEL_DERIVATION'})
                if t['final_observation']['prescription']=='ATTESTED':
                    mutant=copy.deepcopy(m);mutant['observer']['tokens']['performed']=mutant['observer']['tokens']['prescribed']
                    wrong=observe_state(mutant,t['final_state'])
                    stores['counterexamples'].append({'task_id':task['id'],'kind':'D_PRESCRIPTION_PERFORMANCE_CONFLATED',
                        'state':t['final_state'],'correct':t['final_observation'],'incorrect':wrong,
                        'distinguished':wrong['performance']!=t['final_observation']['performance'],
                        'classification':'ENCODING_CHECK','mutant_is_admissible':False})
            else:
                correct=observe_state(m,m['initial_states'][0]);wrong={**correct,'back_status':'NEGATIVE'}
                stores['counterexamples'].append({'task_id':task['id'],'kind':'D_UNKNOWN_NEGATIVE_CONFLATED',
                    'state':m['initial_states'][0],'correct':correct,'incorrect':wrong,
                    'distinguished':correct['back_status']!=wrong['back_status'],'classification':'ENCODING_CHECK',
                    'mutant_is_admissible':False})
    stores['costs']=[{'branch':k,**v,'paid':0,'LLM_calls':0,'end_to_end_Codex_cost':'NOT_MEASURED'} for k,v in costs.items()]
    for name,rows in stores.items():jsonl(out/(name+'.jsonl'),rows)
    result=derive008(stores,legacy,b0)
    result['journal']=Journal.verify(out/'research-journal.jsonl');save(out/'result.json',result)
    save(out/'source-access.json',vault.access);return result


def derive008(stores: dict, legacy: dict, b0: dict) -> dict:
    traces=[r for r in stores['trace-certificates'] if r['branch']=='C']
    final_traces=[r for r in traces if r['revision']==max(x['revision'] for x in traces if x['task_id']==r['task_id'])]
    has=lambda task,predicate:any(r['task_id']==task and predicate(r) for r in final_traces)
    effects=[w for w in stores['binding-effect-witnesses'] if w['branch']=='C' and w['kind'] in {'DISTINGUISHING_EXECUTION_OR_OBSERVER','REGISTERED_TRACE_DIFFERENCE'}]
    negatives=stores['counterexamples']
    revisions=[r for r in stores['revision-history'] if r['branch']=='C' and r['query_recomputed'] and (r['new_enabled_complete_trace'] or r['new_normative_trace']) and r['previous_model_hashes']!=r['new_model_hashes']]
    gates={'E0':'PENDING_FINAL_REGRESSION','E1':'PASS' if stores['source-target-contracts'] and all(r['contract']['boundary'] and not r['result']['source_claim_verified'] for r in stores['source-target-contracts']) and all(r['all_operations_independently_replayed'] for r in stores['trace-certificates']) and normalized(legacy)==normalized(b0) else 'FAIL',
        'T1':'PASS' if has('R4',lambda r:any(t['all_steps_fired'] and len(t['steps'])>=2 for t in r['traces'])) and has('P4',lambda r:any(t['all_steps_fired'] and t['final_observation'].get('prescription')=='ATTESTED' and t['final_observation'].get('performance')=='UNKNOWN' for t in r['traces'])) and has('P3',lambda r:any(t['final_observation'].get('back_status')=='NEGATIVE' and t['final_observation'].get('outgoing_any_actor') for t in r['traces'])) else 'FAIL',
        'T2':'PASS' if effects else 'FAIL',
        'T3':'PASS' if has('R4',lambda r:bool(r['order_witnesses'])) and has('P4',lambda r:bool(r['order_witnesses'])) and negatives and all(n['distinguished'] for n in negatives) else 'FAIL',
        'T4':'PASS' if revisions else 'FAIL','E2':'PENDING_EXTRACTED_REPLAY'}
    return {'experiment':'LM_DAV_TYPED_REALIZATION_008','status':'PARTIAL_TYPED_REALIZATION','gates':gates,
        'gate_evidence':{'T1':[{'task_id':r['task_id'],'model_hash':r['model_hash'],'trace_ids':[t['trace_id'] for t in r['traces']]} for r in final_traces],
            'T2':[{'models':r['models'],'kind':r['kind'],'dimension':r['dimension']} for r in effects],
            'T3':{'source_deletions':sum(r['kind']=='SOURCE_UNIT_DELETION' for r in negatives),'guard_deletions':sum(r['kind']=='GUARD_ABSENT' for r in negatives)},
            'T4':[{'task_id':r['task_id'],'revision':r['revision'],'before':r['previous_model_hashes'],'after':r['new_model_hashes']} for r in revisions]},
        'eight_legacy_cases_retained':True,'historical':legacy['historical'],
        'original_exact_claims':legacy['SOURCE_CLAIM_SUPPORT'],
        'INCREMENTAL_GAIN':'NO_INCREMENTAL_GAIN_OBSERVED' if all(r['same_final_models'] for r in stores['baseline-comparison']) else 'DIFFERENT_RECONSTRUCTION',
        'SEMANTIC_ADEQUACY':'CONDITIONAL_KNOWN_SOURCE_MODEL_ONLY','AUTONOMOUS_OPERATION_DISCOVERY':'NOT_ESTABLISHED',
        'FRESH_TRANSFER':'NOT_RUN','PHYSICAL_REALIZATION':'NOT_ESTABLISHED',
        'execution_permission':{'allowed':False},'proof_status':'unverified'}
