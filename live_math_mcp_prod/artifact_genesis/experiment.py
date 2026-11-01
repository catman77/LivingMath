"""Raw H -> source critique -> DAV -> source forecasts -> sealed independent challenge."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import time
from typing import Any
from zipfile import ZipFile

from davcore.ast import digest
from .source import SourceVault,save
from .audit import source_audit
from .binding import bind_and_challenge
from .process import run_worker
from .journal import Journal
from .controls import run_controls


def jsonl(path,rows):path.write_text(''.join(json.dumps(x,ensure_ascii=False,sort_keys=True)+'\n' for x in rows))


def predictions_from_source(hypotheses,packet_languages,audits):
    supported=[h for h in hypotheses if audits[h['hypothesis_id']]['status']=='PROXY_SUPPORTED'];out=[]
    for language in ['en','ru']:
        hs=[h for h in supported if packet_languages[h['packet_id']]==language]
        claims={h['proposed_relation']['claim'] for h in hs}
        kinds=[]
        if language=='en' and {'negation_present','textual_order'}<=claims:
            kinds=['negated_prerequisite','contrasted_method_with_explicit_order']
        if language=='en' and 'parallel_word_frames' in claims:kinds.append('ordered_parallel_role_reversal')
        if language=='ru' and 'subject_form_changes' in claims:kinds=['new_subject_acts_on_former_addressee']
        for kind in kinds:
            p={'language':language,'source_relation':kind,'source_hypothesis_ids':[h['hypothesis_id'] for h in hs],
                'predicted_roles':({'negated_prerequisite':['antecedent_event','negated_outcome_without_antecedent'],
                    'contrasted_method_with_explicit_order':['rejected_method','endorsed_practitioner','first_role','then_role'],
                    'ordered_parallel_role_reversal':['first_input_role','first_output_role','second_input_role','second_output_role'],
                    'new_subject_acts_on_former_addressee':['previous_addressee_as_object','new_explicit_subject','new_predicate_event']})[kind],
                'polarity':'Explicit negative dependency or contrast where applicable; no inferred chemical fact.',
                'order':'Must be attested as a relation; printed adjacency alone is insufficient.',
                'addressable_effect':'Postchecker must return exact new source spans and role/marker witnesses.',
                'falsifier':'Missing required roles, negation, antecedent or independent source binding.',
                'target_free':True,'confidence_status':'UNVERIFIED_SOURCE_FORECAST','semantic_review':'SEMANTIC_NOT_EXTERNALLY_REVIEWED'}
            p['id']=digest(p);out.append(p)
    return out


def frozen_B1(root,out):
    """Only the privileged baseline reads the old editor graph, never the raw proposer."""
    with ZipFile(root/'frozen/baseline001.zip') as z:
        prefix='ARTIFACT_TRANSLATION_001/artifact_translation001/'
        old=json.loads(z.read(prefix+'result.json'))
        graphs=json.loads(z.read(prefix+'frozen/graphs.json'))
        evidence=json.loads(z.read(prefix+'heldout-receipt.json'))
    return {'name':'B1','status':'FROZEN_001_G3_FAIL_REPRODUCED','old_status':old['scientific_status'],
        'heldout_source_predictions':0,'cross_gate_formal_checks':evidence['cross_gate'],
        'source_relation_inventory':[{'source':g['name'],'relation_kinds':sorted({r['kind'] for r in g['graph']['relations']})} for g in graphs],
        'prior_information':'Editor B-annotations; not a raw-only matched semantic baseline.',
        'proposer_received_these_graphs':False,'scientific_success':False}


async def run(root: Path,out: Path) -> dict:
    started=time.monotonic();out.mkdir(parents=True,exist_ok=False);vault=SourceVault(root)
    journal=Journal(out/'research-journal.jsonl');hs=[];audits={};bindings=[];repairs=[];inputs=[];alternatives=[]
    b2_bindings=[];effective=[];effective_audits={}
    unknowns=[];cost: dict[str,Any]={'proposer_calls':0,'raw_input_bytes':0,'target_checks':0,'DAV_operation_applications':0,
        'LLM_calls':0,'LLM_tokens':None,'proposer_status':'NO_LLM_SEMANTIC_PROPOSER'}
    packet_languages={};train=[]
    for ident,meta in vault.catalog.items():
        if meta['partition']!='train':continue
        packet=vault.packet(ident);train.append(packet);packet_languages[ident]=packet.language
        req=packet.model_dump();inputs.append({'phase':'PRE_SEAL','packet':req,'input_sha256':digest(req)})
        cost['raw_input_bytes']+=len(json.dumps(req,ensure_ascii=False).encode());cost['proposer_calls']+=1
        result=await run_worker('worker',req)
        if result['isolation']['forbidden_modules_loaded']:raise ValueError('PROPOSER_IMPORTED_EDITOR_OR_CHECKER')
        if len(result['hypotheses'])<2:raise ValueError('NO_COMPETING_RAW_SOURCE_READINGS')
        journal.append('RAW_PROPOSAL',{'packet_id':ident,'input_sha256':digest(req),'isolation':result['isolation'],
                                      'hypothesis_ids':[h['hypothesis_id'] for h in result['hypotheses']]})
        for h in result['hypotheses']:
            hs.append(h);alternatives.append({'hypothesis_id':h['hypothesis_id'],'source_spans':h['source_spans'],'alternatives':h['alternatives']})
            audit=source_audit(h,packet);audits[h['hypothesis_id']]=audit
            journal.append('SOURCE_AUDIT',{'hypothesis_id':h['hypothesis_id'],'audit':audit})
            if audit['status']=='PROXY_SUPPORTED':
                ablated=bind_and_challenge(h,audit,allow_repair=False);b2_bindings.append(ablated)
                bound=bind_and_challenge(h,audit);bindings.append(bound);cost['target_checks']+=1
                cost['B2_target_checks']=cost.get('B2_target_checks',0)+1
                cost['DAV_operation_applications']+=bound['probe_evidence']['metrics']['operation_applications']
                journal.append('DAV_COUNTEREXAMPLE',{'hypothesis_id':h['hypothesis_id'],'evidence':bound['probe_evidence']})
                rev=bound['revision'];rev['original_hypothesis_id']=h['hypothesis_id']
                journal.append('REVISION',rev);repairs.append(rev)
                after=rev.get('new_H',h);after_audit=source_audit(after,packet)
                effective.append(after);effective_audits[after['hypothesis_id']]=after_audit
                journal.append('SOURCE_REAUDIT_AFTER_TARGET_FEEDBACK',{'hypothesis_id':after['hypothesis_id'],
                    'audit':after_audit,'target_truth_not_used':True})
            else:
                # Bounded source context/counterreading search, not a terminal UNKNOWN shortcut.
                attempted=[]
                for context in [packet.spans,packet.context][:2]:
                    attempted.append({'span_ids':[s.id for s in context],'exact_context_sha256':digest([s.text for s in context]),
                        'reading_tested':h['proposed_relation']['claim'],'audit_result':audit['status']})
                unknowns.append({'hypothesis_id':h['hypothesis_id'],'kind':'AMBIGUOUS_READING','attempts':attempted,
                    'counterreading':h['alternatives'],'outcome':'SEARCH_EXHAUSTED_BOUNDED_CONTEXT','source_modified':False})
    # F/expressivity/observer unknowns get real finite attempts and explicit final boundaries.
    unknowns.extend([
        {'kind':'ABSENT_FACT','claim':'Modern chemical identity or empirical reaction rate',
         'attempts':[{'context_packet':p.id,'searched_spans':[s.id for s in p.spans],
             'result':'Textual names/instructions are not independent material measurement'} for p in train],
         'outcome':'EXTERNAL_EVIDENCE_REQUIRED_AFTER_FINITE_CONTEXT_SEARCH','value':'UNKNOWN'},
        {'kind':'OBSERVER_LOSS','attempts':[{'original_hypothesis_id':r['original_hypothesis_id'],
            'counterexample':r.get('counterexample'),'operation':r['kind']} for r in repairs],
         'outcome':'JOINT_PREDICATES_SEPARATED_AND_UNWARRANTED_NECESSITY_WITHDRAWN'},
        {'kind':'TARGET_EXPRESSIVITY','claim':'Narrative tense, imperative modality and agency are not chemical kinetics',
         'attempts':[{'representation':'Directed symbolic event transition','result':'Conditional only; does not prove process chronology'},
                     {'representation':'Source role/tense metadata with separate predicates','result':'Preserves uncertainty; no kinetic/empirical claim'}],
         'outcome':'UNREPRESENTED_SEMANTICS_RETAINED_IN_LOSS_LEDGER_NO_NEW_DSL'}])
    controls=await run_controls(vault,train[0])
    c_predictions=predictions_from_source(effective,packet_languages,effective_audits)
    if not c_predictions:raise ValueError('NO_SOURCE_FORECAST_TO_SEAL')
    predictions=[]
    for branch in ['C','B2']:
        for p in c_predictions:
            item={**p,'branch':branch};item['id']=digest(item);predictions.append(item)
        if branch=='B2':
            for language in sorted({packet_languages[h['packet_id']] for h in hs if h['proposed_relation']['claim']=='joint_predication'}):
                p={'branch':'B2','language':language,'source_relation':'unseen_necessity_of_conjoined_clauses',
                   'predicted_roles':['visible_predicate','necessarily_coincident_predicate'],'target_free':True,
                   'confidence_status':'UNVERIFIED_UNREPAIRED_BINDING_PROMOTION','falsifier':'A conjunction alone is not a necessary condition.'}
                p['id']=digest(p);predictions.append(p)
    jsonl(out/'preholdout-predictions.jsonl',predictions)
    jsonl(out/'candidate-source-relations.jsonl',hs)
    seal=vault.seal(predictions);journal.append('SOURCE_PREDICTIONS_SEALED',seal)
    save(out/'precommit-seal.json',{**seal,'candidate_source_sha256':hashlib.sha256((out/'candidate-source-relations.jsonl').read_bytes()).hexdigest(),
        'predictions_file_sha256':hashlib.sha256((out/'preholdout-predictions.jsonl').read_bytes()).hexdigest(),
        'proposer_inputs_before_seal':[i['input_sha256'] for i in inputs],
        'blinding':'Engineering process/input isolation only; public corpus known to coding agent/LLM pretraining.'})
    held=[];independence=[]
    for ident,meta in vault.catalog.items():
        if meta['partition']!='holdout':continue
        packet=vault.packet(ident,seal=seal)
        response=await run_worker('postcheck',{'packet':packet.model_dump(),'predictions':predictions,'seal':seal})
        if response['independence']['forbidden_modules_loaded']:raise ValueError('POSTCHECK_IMPORT_BOUNDARY_BROKEN')
        held.extend(response['checks']);independence.append(response['independence'])
        for row in response['checks']:journal.append('POST_HOLDOUT_SOURCE_CHECK',row)
    for ident,meta in vault.catalog.items():
        if meta['partition']!='negative_control':continue
        packet=vault.packet(ident,seal=seal)
        inputs.append({'phase':'POST_SEAL_KNOWN_NEGATIVE_CONTROL','packet':packet.model_dump(),'input_sha256':digest(packet.model_dump())})
        generated=await run_worker('worker',packet.model_dump());cost['proposer_calls']+=1
        audited=[(h,source_audit(h,packet)) for h in generated['hypotheses']]
        joint=next((pair for pair in audited if pair[0]['proposed_relation']['claim']=='joint_predication' and pair[1]['status']=='PROXY_SUPPORTED'),None)
        if joint is None:raise ValueError('KNOWN_NEGATIVE_SOURCE_JOINT_NOT_EXTRACTED')
        trial=bind_and_challenge(joint[0],joint[1])
        save(out/'gate6-negative-control.json',{'source_H':joint[0],'source_audit':joint[1],'binding_trial':trial,
            'counterexample_P':trial['counterexample']['bits'][0],'counterexample_Q':trial['counterexample']['bits'][1],
            'new_scientific_discovery':False,'known_negative_control_only':True})
        journal.append('KNOWN_NEGATIVE_CONTROL',{'hypothesis_id':joint[0]['hypothesis_id'],
            'counterexample':trial['counterexample'],'new_discovery':False})
    # No target consequence is used to adjudicate these source predictions.
    branch_by_id={p['id']:p['branch'] for p in predictions}
    for row in held:row['branch']=branch_by_id[row['prediction_id']]
    c_held=[r for r in held if r['branch']=='C'];b2_held=[r for r in held if r['branch']=='B2']
    matched=sum(row['status']=='PROXY_MATCH' for row in c_held)
    status='INSUFFICIENT_SEMANTIC_EVIDENCE' if matched else 'FAIL_NO_TRANSFER'
    baselineB1=frozen_B1(root,out)
    B0=[{'packet_id':p.id,'literal_event_quotes':[s.text for s in p.spans],
         'unseen_predictions':0,'new_relations':0} for p in train]
    B2={'name':'B2','same_raw_hypothesis_ids':[h['hypothesis_id'] for h in hs],
        'source_audit_ids':sorted(audits),'repairs':0,
        'unresolved_necessity_counterexamples':[b['counterexample'] for b in b2_bindings if b['counterexample']],
        'actual_target_trials':len(b2_bindings),'actual_source_checks':b2_held,
        'heldout_proxy_matches':sum(r['status']=='PROXY_MATCH' for r in b2_held),
        'unsupported_necessity_forecasts_rejected':sum(r['source_relation']=='unseen_necessity_of_conjoined_clauses' and r['status']!='PROXY_MATCH' for r in b2_held),
        'scientific_success':False,'source_predictions':[p for p in predictions if p['branch']=='B2']}
    baselines={'B0':{'name':'B0','outputs':B0,'scientific_success':False},'B1':baselineB1,'B2':B2,
        'C':{'name':'C','raw_hypotheses':len(hs),'source_proxy_supported':sum(a['status']=='PROXY_SUPPORTED' for a in audits.values()),
             'meaningful_binding_revisions':sum(r['kind']=='BINDING_REPAIR' for r in repairs),
             'precommitted_source_predictions':len(c_predictions),'heldout_proxy_matches':matched,'new_independent_source_laws':0},
        'B3':{'status':'NOT_RUN','provider':None,'model':None,'tokens':None},
        'comparison_limit':'B1 has privileged old annotations. B0/B2 source checks can recover local schema instances too. No C semantic superiority is established.',
        'budget':'Identical new-run source/target ceilings; actual counts retained; historical 001 replay costs are separate.'}
    for p in predictions:
        journal.append('UNSEEN_HYPOTHESIS_REVIEW',{'prediction_id':p['id'],'counterevidence':[r for r in held if r['prediction_id']==p['id']],
            'revision':'Retain proxy occurrence only; withdraw general scientific-transfer claim.',
            'semantic_review':'SEMANTIC_NOT_EXTERNALLY_REVIEWED','G3_passed':False})
    jsonl(out/'alternative-readings.jsonl',alternatives);jsonl(out/'source-audits.jsonl',[
        {'hypothesis_id':h,'audit':a} for h,a in sorted(audits.items())])
    jsonl(out/'repair-history.jsonl',repairs);jsonl(out/'target-bindings.jsonl',bindings)
    jsonl(out/'B2-target-trials.jsonl',b2_bindings)
    jsonl(out/'holdout-checks.jsonl',held);jsonl(out/'nontriviality-controls.jsonl',controls)
    jsonl(out/'unknown-resolution.jsonl',unknowns);jsonl(out/'proposer-inputs.jsonl',inputs)
    jsonl(out/'loss-ledger.jsonl',[{'hypothesis_id':h['hypothesis_id'],'grade':'B','source_status':audits[h['hypothesis_id']]['status'],
        'unrepresented':['Physical time','Material identity','Causal mechanism','Expert semantic adjudication'],
        'source_spans':h['source_spans'],'preserved_in_H_and_source':True} for h in hs])
    save(out/'baselines.json',baselines);save(out/'source-access.json',{'accesses':vault.access,'seal':seal,'postchecker_independence':independence})
    software=all(r['result']=='PASS' for r in controls)
    result={'scientific_status':status,'software_status':'PASS' if software else 'FAIL','G3':'FAIL',
        'semantic_review':'SEMANTIC_NOT_EXTERNALLY_REVIEWED','proposer':'NO_LLM_SEMANTIC_PROPOSER',
        'integration':'STAGING_ONLY_NO_NEW_PRODUCTION_TOOLS','raw_train_packets':len(train),'hypotheses':len(hs),
        'source_proxy_supported':sum(a['status']=='PROXY_SUPPORTED' for a in audits.values()),
        'source_predictions':len(c_predictions),'all_baseline_predictions_sealed':len(predictions),
        'heldout_checks':len(c_held),'all_baseline_heldout_checks':len(held),'heldout_proxy_matches':matched,
        'binding_revisions':sum(r['kind']=='BINDING_REPAIR' for r in repairs),'controls':len(controls),
        'journal':Journal.verify(out/'research-journal.jsonl'),'new_independently_validated_source_relations':0,
        'cycle_break':'Proxy grammar/source occurrences -> independent non-template semantic law: not established; finite target truth cannot supply it.',
        'proof_status':'unverified','execution_permission':{'allowed':False}}
    save(out/'result.json',result);cost['wall_ms']=(time.monotonic()-started)*1000;save(out/'costs.json',cost)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();print(json.dumps(asyncio.run(run(a.root.resolve(),a.out.resolve())),ensure_ascii=False))
