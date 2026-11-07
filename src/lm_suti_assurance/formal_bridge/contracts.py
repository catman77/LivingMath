"""Additive bounded MCP contracts; semantic validators run inside isolated worker."""

from ..symbolic.contracts import obj,arr,integer,PROJECT,KEY,REF
from .ir import DEFAULTS

BOUNDS=obj({k:integer(1,n) for k,n in DEFAULTS.items()})
ANY={'type':'object'}
SOURCE=obj({'text_utf8':{'type':'string','maxLength':48000},'sha256':REF,'spans':arr(ANY,128),'context_refs':arr(REF,32),'rights':{'type':'string','minLength':1,'maxLength':2048}},['text_utf8','sha256','spans','context_refs','rights'])
PROVIDER=obj({'kind':{'enum':['human','imported','white_star','external_llm']},'provenance':ANY},['kind','provenance'])
COMMON={'project':PROJECT,'request_key':KEY,'budget':BOUNDS}
TOOLS={
 'formal_store':obj({**COMMON,'kind':{'enum':['source','model','record','grammar','dfa','proof']},'data':ANY},['project','request_key','kind','data']),
 'formal_synthesize':obj({**COMMON,'train_ref':REF,'predict_ref':REF,'constraints':obj({'kind':{'enum':['cfg','dfa']}},['kind'])},['project','request_key','train_ref','predict_ref','constraints']),
 'formal_inspect':obj({'project':PROJECT,'run_ref':REF,'view':{'enum':['summary','result','model','candidates','predictions','considered','objects','object','packet','bundle']},'object_ref':REF,'offset':integer(0,10000000),'limit':integer(1,128)},['project','run_ref']),
 'formal_verify':obj({**COMMON,'run_ref':REF,'candidate_ref':REF,'source_ref':REF,'proof_ref':REF},['project','request_key','run_ref','source_ref']),
 'formal_contrast':obj({**COMMON,'run_ref':REF,'candidate_refs':arr(REF,16,2)},['project','request_key','run_ref','candidate_refs']),
 'formal_interpret':obj({**COMMON,'source_ref':REF,'candidate_provider':PROVIDER,'target_signature':ANY,'proposals':arr(ANY,16,1)},['project','request_key','source_ref','candidate_provider','target_signature','proposals']),
 'formal_model_check':obj({**COMMON,'run_ref':REF,'candidate_ref':REF,'model_ref':REF},['project','request_key','run_ref','candidate_ref','model_ref']),
 'formal_replay':obj({**COMMON,'run_ref':REF},['project','request_key','run_ref']),
}
