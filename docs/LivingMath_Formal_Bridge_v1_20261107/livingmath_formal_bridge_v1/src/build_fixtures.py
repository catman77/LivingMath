#!/usr/bin/env python3
"""Freeze a source-aligned, manually annotated NL pilot and formal grammar oracles.
Candidate interpretations here are authored fixtures, NOT inferred from Russian.
"""
from __future__ import annotations
import hashlib, json
from pathlib import Path
from reference_kernel import GRAMMARS,INTERPRETATIONS,SIGNATURE,parse,truth_vector,model

ROOT=Path(__file__).resolve().parent.parent/'fixtures'
ROOT.mkdir(exist_ok=True)

def save(name,obj):
    (ROOT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')

def span(s,needle):
    i=s.index(needle)
    j=i+len(needle)
    return {'literal':needle,'codepoint':[i,j],
            'byte_utf8':[len(s[:i].encode('utf8')),len(s[:j].encode('utf8'))]}

phrase='Каждый исследователь проверил одну гипотезу.'
rows=[
    {'candidate_id':k,'formula_ast':v,'annotation_origin':'HAND_AUTHORED_ORACLE',
     'source_token_links':[span(phrase,'Каждый'),span(phrase,'одну')],
     'formalization_status':'PROPOSED_MANUAL_NOT_NL_DISCOVERED',
     'type_status':'CHECKED_REFERENCE',
     'model_truth_status':'EVALUABLE_FINITE'}
    for k,v in INTERPRETATIONS.items()
]
M1=model(('r1','r2'),('h1','h2'),(('r1','h1'),('r2','h2')))
M2=model(('r1','r2'),('h1','h2'),(('r1','h1'),('r1','h2'),('r2','h1')))
save('quantifier_ambiguity.json',{
    'schema':'livingmath-nl-formal-fixture/1',
    'source':{'text':phrase,'sha256':hashlib.sha256(phrase.encode()).hexdigest(),
              'rights':'synthetic-original-controlled-example','language':'ru'},
    'signature':SIGNATURE,'nonempty_sorts':['researcher','hypothesis'],
    'open_world_real_facts_not_assumed':True,
    'candidate_generation_status':'NOT_EXECUTED_ON_LIVE_MCP',
    'candidates':rows,
    'finite_models':[{'name':'different_hypotheses','model':M1,'truth_vector':truth_vector(M1)},
                     {'name':'common_but_one_researcher_checks_two','model':M2,'truth_vector':truth_vector(M2)}],
    'limit':'No claim that any candidate captures authors intended meaning',
})

save('grammar_oracles.json',{
    'schema':'livingmath-reference-grammar-fixture/1',
    'warning':'REFERENCE ORACLES ONLY. DO NOT import these definitions into production synthesis.',
    'grammars':{key:{'start':g.start,'rules':{nt:[list(rhs) for rhs in prods] for nt,prods in g.rules.items()}}
                for key,g in GRAMMARS.items()}
})

chosen_examples={
    'dyck2':['S','A','B','P'],
    'even_palindrome':['a','b','b','a'],
    'anbn_nonempty':['a','a','b','b'],
    'ambiguous_concat':['a','a','a'],
}
save('parse_witness_examples.json',{
   'warning':'Witnesses independently checked by run_acceptance.py; these are reference trees, not discovered by live MCP.',
   'examples':{name:{'word':w,'trees':parse(GRAMMARS[name],tuple(w),limit=16).trees}
               for name,w in chosen_examples.items()},
})

report=json.loads((ROOT.parent/'results'/'reference_acceptance.json').read_text(encoding='utf8'))
save('active_queries.json',{
    'schema':'livingmath-active-contrast-oracle/1',
    'generated_by':'finite enumeration of explicit reference candidates',
    'warning':'Absence of a differentiating word up to N cannot prove CFG equivalence.',
    'contrasts':report['distinguishers'],
})

save('synthesis_contract.json',{
   'status':'TO_IMPLEMENT_NOT_CURRENT_MCP_API',
   'grammar_primitives':['EPS','TERM','NT_REF','SEQ','ALT'],
   'automaton_primitives':['STATE','TRANSITION','ACCEPTING_STATE'],
   'candidate_bound_example':{'max_grammar_nt':2,'max_rules':6,'max_rhs_symbols':5,
                              'max_ast_nodes':32,'max_parser_tokens':12,
                              'max_cpu_ms_per_run':4000,'stop':'UNKNOWN_BOUND'},
   'induction_allowed_input':['train.tokens','train.accepted','train.source_sha256'],
   'held_out_input':['query.tokens','query.source_sha256'],
   'held_out_forbidden':['query.accepted','query.class_name','oracle_grammar'],
   'output_requirements':['grammar_ast','parse_witness','source_spans','candidate_status',
                          'untried_bound','countermodels','replay_hash'],
   'security':['no_execute_source_text','strict_sha256','no_secret_exfiltration'],
})
print('Fixtures written', sorted(x.name for x in ROOT.iterdir()))
