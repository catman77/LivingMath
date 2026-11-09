"""Strict additive contracts; resource and exact-source validation before journaling."""
from ...symbolic.contracts import obj,arr,integer,PROJECT,KEY,REF
from ...core import canonical
from ...formal_bridge.fol import check_source,check_link
from ...symbolic.state import require

TEXT={'type':'string','minLength':1,'maxLength':2048}
ID={'type':'string','pattern':'^[A-Za-z][A-Za-z0-9_-]{0,47}$'}
TERM=obj({'var':{'type':'string','minLength':1,'maxLength':128}},['var'])
AST=obj({'quant':{'enum':['forall','exists']},'var':{'type':'string','minLength':1,'maxLength':128},'sort':{'type':'string','maxLength':128},'body':{'$ref':'#/$defs/ast'},'pred':{'type':'string','maxLength':128},'args':arr(TERM,3),'eq':arr(TERM,2,2),'not':{'$ref':'#/$defs/ast'},'and':arr({'$ref':'#/$defs/ast'},16,1),'or':arr({'$ref':'#/$defs/ast'},16,1),'future':{'$ref':'#/$defs/ast'}})
LINK=obj({'byte_utf8':arr(integer(0,48000),2,2),'literal':{'type':'string','maxLength':48000},'ast_path':arr({'oneOf':[{'type':'string','maxLength':128},integer(0,128)]},32),'role':TEXT},['byte_utf8','literal'])
OBLIGATION=obj({'id':ID,'kind':{'enum':['PRESUPPOSITION','ANAPHORA','SCOPE','NEGATION_SCOPE','TEMPORALITY','LANGUAGE_GAP','CONTEXT','LEXICAL_ASSUMPTION']},'description':TEXT,'source_links':arr(LINK,16),'status':{'const':'OPEN'},'assumption_ast':{'$ref':'#/$defs/ast'}},['id','kind','description','status'])
TRACE=obj({k:TEXT for k in ['origin','status','candidate','description','note','provider']});TRACE['minProperties']=1
UNSUPPORTED=obj({'operator':TEXT,'source_fragment':{'type':'string','minLength':1,'maxLength':48000},'reason':TEXT},['operator','source_fragment','reason'])
HYPOTHESIS=obj({'client_id':ID,'source_ref':REF,'language':{'const':'FOL_V1'},'formula_ast':{'$ref':'#/$defs/ast'},'unsupported':UNSUPPORTED,'assumptions':arr({'$ref':'#/$defs/ast'},16),'source_links':arr(LINK,16,1),'construction_trace':arr(TRACE,64,1),'obligations':arr(OBLIGATION,8),'creator':{'enum':['external_llm','human','imported']}},['client_id','language','assumptions','source_links','construction_trace','obligations'])
HYPOTHESIS['oneOf']=[{'required':['formula_ast'],'not':{'required':['unsupported']}},{'required':['unsupported'],'not':{'required':['formula_ast']}}]
SIGNATURE=obj({'sorts':arr({'type':'string','minLength':1,'maxLength':128},4,1),'predicates':{'type':'object','maxProperties':4,'propertyNames':{'type':'string','minLength':1,'maxLength':128},'additionalProperties':arr({'type':'string','maxLength':128},3,1)}},['sorts','predicates'])
BUDGET=obj({'max_pairs':integer(1,10),'max_models':integer(1,512),'max_cpu_ms':integer(1,4000),'max_steps':integer(1,100000),'max_atoms':integer(1,10)})
PAIR=arr({'oneOf':[ID,REF]},2,2)
TOOLS={
'semantic_bridge_register':obj({'project':PROJECT,'request_key':KEY,'source_ref':REF,'expected_source_sha256':REF,'target_signature':SIGNATURE,'hypotheses':arr(HYPOTHESIS,6,1)},['project','request_key','source_ref','expected_source_sha256','target_signature','hypotheses']),
'semantic_bridge_analyze':obj({'project':PROJECT,'request_key':KEY,'batch_ref':REF,'pairs':arr(PAIR,10),'model_refs':arr(REF,8),'scenario_origin':{'enum':['LLM_PROPOSED','HUMAN_PROVIDED']},'budget':BUDGET},['project','request_key','batch_ref','pairs','model_refs']),
'semantic_bridge_inspect':obj({'project':PROJECT,'batch_or_run_ref':REF,'view':{'enum':['summary','graph','obligations','checks','bundle']},'offset':integer(0,33554432),'limit':integer(1,48),'expected_result_sha256':REF},['project','batch_or_run_ref']),
'semantic_bridge_replay':obj({'project':PROJECT,'run_ref':REF,'expected_result_sha256':REF},['project','run_ref','expected_result_sha256'])}
for schema in TOOLS.values():schema['$defs']={'ast':AST}


def guard(value):
    stack=[(value,0)];nodes=0
    while stack:
        v,depth=stack.pop();nodes+=1
        require(depth<=48 and nodes<=20000,'INPUT_COMPLEXITY_BOUND')
        if isinstance(v,dict):stack.extend((x,depth+1) for x in v.values())
        elif isinstance(v,list):stack.extend((x,depth+1) for x in v)
    require(len(canonical(value).encode())<=262144,'INPUT_BYTES_BOUND')


def validate(tool,args):
    guard(args)
    from jsonschema import Draft202012Validator
    error=next(Draft202012Validator(TOOLS[tool]).iter_errors(args),None)
    require(error is None,'INVALID_INPUT','/'+('/'.join(map(str,error.path)) if error else ''))


def source_bindings(args,source):
    check_source(source);require(source['sha256']==args['expected_source_sha256'],'SOURCE_BINDING_MISMATCH')
    require(len({h['client_id'] for h in args['hypotheses']})==len(args['hypotheses']),'DUPLICATE_CLIENT_ID')
    for h in args['hypotheses']:
        require(h.get('source_ref',args['source_ref'])==args['source_ref'],'SOURCE_BINDING_MISMATCH')
        require(len({o['id'] for o in h['obligations']})==len(h['obligations']),'DUPLICATE_OBLIGATION_ID')
        for item in [h,*h['obligations']]:
            for link in item.get('source_links',[]):
                check_link(source,{k:link[k] for k in ['byte_utf8','literal']})
                if 'ast_path' in link:
                    node=item.get('assumption_ast',h.get('formula_ast'))
                    require(node is not None,'INVALID_AST_PATH')
                    for k in link['ast_path']:
                        require((isinstance(node,dict) and type(k) is str and k in node) or (isinstance(node,list) and type(k) is int and 0<=k<len(node)),'INVALID_AST_PATH');node=node[k]
        if 'unsupported' in h:require(h['unsupported']['source_fragment'] in source['text_utf8'],'SOURCE_FRAGMENT_MISMATCH')
