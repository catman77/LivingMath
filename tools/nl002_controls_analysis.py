"""Post-freeze measurement of pre-specified renamed and lexical control sources."""
import argparse,json
from pathlib import Path
from nl002_score import alpha,stable
from nl002_independent_checker import vectors

def rename_ast(ast,sorts,predicates):
 if isinstance(ast,list):return [rename_ast(v,sorts,predicates) for v in ast]
 if not isinstance(ast,dict):return ast
 return {k:sorts.get(v,v) if k=='sort' else predicates.get(v,v) if k=='pred' else rename_ast(v,sorts,predicates) for k,v in ast.items()}
def rename_sig(sig,sorts,preds):return {'sorts':[sorts.get(s,s) for s in sig['sorts']],'predicates':{preds.get(p,p):[sorts.get(s,s) for s in ss] for p,ss in sig['predicates'].items()}}
def same_sig(a,b):return set(a['sorts'])==set(b['sorts']) and a['predicates']==b['predicates']
def pattern(text):
 d={};return [d.setdefault(t,len(d)) for t in text.split()]
def symbols(ast,key):
 if isinstance(ast,list):return set().union(*(symbols(v,key) for v in ast)) if ast else set()
 if not isinstance(ast,dict):return set()
 return ({ast[key]} if key in ast else set())|set().union(*(symbols(v,key) for v in ast.values()))
def main(a):
 data=json.loads(a.candidates.read_text());sources=json.loads(a.sources.read_text())['sources'];gold=json.loads(a.gold.read_text());byid={s['id']:s for s in sources};report={'status':'MEASURED_POST_FREEZE','human_semantic_accuracy':None,'semantic_generalization':'NOT_EVALUATED','renamed_pairs':[],'lexical_alpha_pair':[]}
 for arm,jobs in data.items():
  outputs={i['source_sha256']:i for job in jobs for i in job['result']['items']}
  for pair in gold['renamed_pair_maps']:
   left,right=[byid[x] for x in pair['source_ids']];ss=pair['sort_renaming'];ps=pair['predicate_renaming']
   if not same_sig(rename_sig(left['signature'],ss,ps),right['signature']):
    assert same_sig(rename_sig(right['signature'],ss,ps),left['signature']);left,right=right,left
   lhs=[rename_ast(c['formula_ast'],ss,ps) for c in outputs[left['sha256']]['candidates']];rhs=[c['formula_ast'] for c in outputs[right['sha256']]['candidates']]
   assert all(symbols(c,'pred')<=set(right['signature']['predicates']) and symbols(c,'sort')<=set(right['signature']['sorts']) for c in lhs+rhs)
   la={stable(alpha(c)) for c in lhs};ra={stable(alpha(c)) for c in rhs};lv=[vectors(c,right['signature']) for c in lhs];rv=[vectors(c,right['signature']) for c in rhs];all_comparable=None not in lv+rv
   report['renamed_pairs'].append({'arm':arm,'pair_id':pair['pair_id'],'source_ids':[left['id'],right['id']],'left_candidates':len(lhs),'right_candidates':len(rhs),'typed_signature_covariance':'PASS','exact_alpha_AST_set_covariance':la==ra,'nonempty_comparison':bool(la or ra),'bounded_vector_set_covariance':set(map(tuple,lv))==set(map(tuple,rv)) if all_comparable else None,'bounded_vectors_not_equivalence_proof':True,'semantic_invariance':'NOT_ESTABLISHED'})
  lexical=[s for s in sources if s['family']=='adversarial_verb'];assert len(lexical)==2
  x,y=lexical;assert x['sha256']!=y['sha256']
  report['lexical_alpha_pair'].append({'arm':arm,'source_ids':[x['id'],y['id']],'same_alpha_pattern':pattern(x['text'])==pattern(y['text']),'literal_source_SHA_distinct':True,'source_refs_distinct':outputs[x['sha256']]['source_ref']!=outputs[y['sha256']]['source_ref'],'typed_predicate_sets':[sorted(set().union(*(symbols(c['formula_ast'],'pred') for c in outputs[s['sha256']]['candidates']))) for s in lexical],'declared_predicates':[sorted(s['signature']['predicates']) for s in lexical],'no_semantic_equality_claim':True})
 report['summary']={arm:{'pairs':len([x for x in report['renamed_pairs'] if x['arm']==arm]),'exact_AST_set_covariant':sum(x['exact_alpha_AST_set_covariance'] for x in report['renamed_pairs'] if x['arm']==arm),'bounded_vector_set_covariant':sum(x['bounded_vector_set_covariance'] is True for x in report['renamed_pairs'] if x['arm']==arm)} for arm in data}
 a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report['summary']))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--candidates',type=Path,required=True);p.add_argument('--sources',type=Path,required=True);p.add_argument('--gold',type=Path,required=True);p.add_argument('--output',type=Path,required=True);main(p.parse_args())
