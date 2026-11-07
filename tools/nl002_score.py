"""Unseal ONLY after complete candidate freeze; synthetic checks are not NL accuracy."""
import argparse,hashlib,json,os
from pathlib import Path
from datetime import datetime,timezone
from nl002_independent_checker import evaluate,vectors

def alpha(ast,env=None):
 env={} if env is None else env
 if 'quant' in ast:
  name='v'+str(len(env));return {'quant':ast['quant'],'var':name,'sort':ast['sort'],'body':alpha(ast['body'],{**env,ast['var']:name})}
 if set(ast)=={'var'}:return {'var':env[ast['var']]}
 return {k:[alpha(x,env) for x in v] if isinstance(v,list) else alpha(v,env) if isinstance(v,dict) else v for k,v in ast.items()}
def stable(x):return json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':'))
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()

def main(a):
 frozen=a.run/'CANDIDATES_FROZEN.json';seal=json.loads((a.run/'CANDIDATES_FREEZE.json').read_text());assert frozen.exists() and sha(frozen)==seal['sha256']
 protocol=json.loads(a.protocol.read_text());assert sha(a.sources)==protocol['public_sources_sha256']
 sources=json.loads(a.sources.read_text())['sources'];runs=json.loads(frozen.read_text());assert set(runs)==set('ABCD') and all(sum(len(j['result']['items']) for j in runs[arm])==len(sources) for arm in 'ABCD')
 # This is the first read of private gold, after all four arms are immutable.
 os.chmod(a.gold,0o600);assert sha(a.gold)==protocol['gold_sha256'];gold=json.loads(a.gold.read_text());a.output.mkdir(parents=True,exist_ok=True)
 save=lambda n,x:(a.output/n).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
 save('GOLD_OPEN_RECEIPT.json',{'utc':datetime.now(timezone.utc).isoformat(),'candidate_freeze_sha256':sha(frozen),'gold_sha256':sha(a.gold),'sources_sha256':sha(a.sources),'gold_previously_visible_to_generator':False,'isolation':'Independent agent procedural split, same OS owner; not cryptographic access isolation','human_adjudication':'NOT_EXECUTED'})
 labels={x['source_id']:x for x in gold['gold']};matrix={};alignment=[];checker=[];contrasts=[];costs=[]
 for arm,jobs in runs.items():
  row={'arm':arm,'N_sources':len(sources),'N_allowed_readings_gold':sum(len(labels[s['id']]['reference_readings']) for s in sources),'N_generated':0,'N_Typed':0,'N_trace_verified':0,'N_source_supported_external':None,'N_contrast_found':0,'N_abstain':0,'N_rejected':0,'N_unknown':0,'N_hallucinated_unlicensed':None,'N_false_equivalence':0,'N_external_annotation_missing':len(sources),'synthetic_alpha_reference_matches':0,'synthetic_finite_vector_matches':0,'synthetic_reference_coverage':0,'synthetic_comparable_references':0,'synthetic_non_reference_vector_matches':0,'model_calls':0,'input_tokens':0,'output_tokens':0,'human_semantic_accuracy':None,'semantic_generalization':'NOT_EVALUATED','cases':[]}
  flat=[i for j in jobs for i in j['result']['items']];assert len(flat)==len(sources)
  for job in jobs:
   r=job['result'];receipt=r['receipt'];u=receipt.get('usage') or {};row['model_calls']+=receipt['model_calls'];row['input_tokens']+=u.get('input_tokens',0);row['output_tokens']+=u.get('output_tokens',0)
   costs.append({'arm':arm,'run_ref':job['run_ref'],'receipt':receipt,'cost_USD':None})
   byast={c['candidate_id']:c['formula_ast'] for i in r['items'] for c in i['candidates']}
   for evidence in job.get('contrasts',[]):
    c=evidence['result'];contrasts.append({'arm':arm,**evidence})
    if c['status']=='FINITE_COUNTERMODEL':
     truth=[evaluate(byast[i],c['model']) for i in c['candidate_ids']];ok=truth==c['truth_vector'] and len(set(truth))>1;checker.append({'run_ref':evidence['run_ref'],'status':'PASS' if ok else 'FAIL','actual_truth_vector':truth,'claimed_truth_vector':c['truth_vector'],'checker':'tools/nl002_independent_checker.py','independent_of_production_evaluator':True});assert ok;row['N_contrast_found']+=1
    elif c['status'].startswith('UNKNOWN'):row['N_unknown']+=1
  for source,result in zip(sources,flat):
   assert source['sha256']==result['source_sha256'];g=labels[source['id']];sig=source['signature'];cs=result['candidates'];refs=g['reference_readings'];nonrefs=g['non_reference_readings'];row['N_generated']+=len(result['raw_proposals']);row['N_Typed']+=len(cs);row['N_rejected']+=len(result['rejected_moves']);row['N_abstain']+=not bool(cs);row['N_trace_verified']+=sum(c['origin_status']=='TRACE_LINK_CHECKED' for c in cs)
   alphas={stable(alpha(c['formula_ast'])) for c in cs};goldalpha={stable(alpha(g['ast'])) for g in refs};matches=len(alphas&goldalpha);row['synthetic_alpha_reference_matches']+=matches
   generated=[vectors(c['formula_ast'],sig) for c in cs];reference=[vectors(x['ast'],sig) for x in refs];bad=[vectors(x['ast'],sig) for x in nonrefs];covered=sum(v is not None and v in generated for v in reference);comparable=sum(v is not None for v in reference);agrees=sum(v is not None and v in reference for v in generated);badmatches=sum(v is not None and v in bad for v in generated)
   row['synthetic_reference_coverage']+=covered;row['synthetic_comparable_references']+=comparable;row['synthetic_finite_vector_matches']+=agrees;row['synthetic_non_reference_vector_matches']+=badmatches
   case={'source_id':source['id'],'family':source['family'],'source_sha256':source['sha256'],'generated':len(cs),'alpha_reference_matches':matches,'bounded_vector_reference_matches':agrees,'bounded_reference_covered':covered,'bounded_comparable_references':comparable,'bounded_nonreference_matches':badmatches,'status':result['status'],'semantic_accuracy':None,'external_adjudication':'NOT_EXECUTED'};row['cases'].append(case)
   alignment.append({'arm':arm,**case,'candidates':[{'candidate_id':c['candidate_id'],'candidate_ast_sha':c['candidate_ast_sha'],'origin_status':c['origin_status'],'type_status':c['type_status'],'semantic_alignment_status':c['semantic_alignment_status'],'source_spans':c['source_spans'],'moves':c['structural_move_log']} for c in cs]})
  row['coverage_interpretation']='Synthetic finite-domain vector coverage only; no logical equivalence or human semantic accuracy';matrix[arm]=row
 save('ARM_ABLATION_MATRIX.json',{'status':'COMPLETED_SYNTHETIC_TECHNICAL_ONLY','matched_nominal_budgets':True,'fixed_model_revision':False,'actual_cost_equal':False,'model_calls_equal':len({r['model_calls'] for r in matrix.values()})==1,'white_star_incremental_benefit':'WHITE_STAR_INCREMENTAL_BENEFIT_NOT_ESTABLISHED','semantic_generalization':'NOT_EVALUATED','human_adjudication':'EXTERNAL_ADJUDICATION_NOT_EXECUTED','arms':matrix})
 save('SOURCE_ALIGNMENT_MATRIX.json',alignment);save('MODEL_CONTRAST_EVIDENCE.json',contrasts);save('INDEPENDENT_CHECKER_RECEIPTS.json',checker);save('PROMPTS_MODEL_RECEIPTS_AND_COSTS.json',costs)
 table=['# Результаты A/B/C/D','', 'Эталон независимый синтетический; человеческая смысловая точность не измерена.','', '| Плечо | Источники | Typed | Trace-linked | Abstain | Finite contrast | Synthetic coverage | Model calls |', '|---|---:|---:|---:|---:|---:|---:|---:|']
 for arm,r in matrix.items():table.append(f"| {arm} | {r['N_sources']} | {r['N_Typed']} | {r['N_trace_verified']} | {r['N_abstain']} | {r['N_contrast_found']} | {r['synthetic_reference_coverage']}/{r['synthetic_comparable_references']} | {r['model_calls']} |")
 table+=['','Совпадение конечных truth vectors не доказывает логическую эквивалентность.','`WHITE_STAR_INCREMENTAL_BENEFIT_NOT_ESTABLISHED`.','`PARTIAL; semantic generalization NOT_EVALUATED; EXTERNAL_ADJUDICATION_NOT_EXECUTED`.'];(a.output/'RESULTS_B_C_RU.md').write_text('\n'.join(table)+'\n')
 print('ALL_ARMS_SCORED_NO_HUMAN_SEMANTIC_CLAIM', {k:r['N_Typed'] for k,r in matrix.items()})

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--protocol',type=Path,required=True);p.add_argument('--sources',type=Path,required=True);p.add_argument('--gold',type=Path,required=True);p.add_argument('--output',type=Path,required=True);main(p.parse_args())
