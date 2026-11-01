"""Actual installed profile hashes and bounds, separate from service/ledger versions."""
import hashlib
from pathlib import Path

from davcore.ast import digest
from davcore.versioning import backend_binding


def capabilities(semantic_provider=None) -> dict:
    root=Path(__file__).resolve().parent.parent
    files=['semantic_repair/'+n for n in ['observe009.py','observe008.py','observe005.py','alignment.py','compiler.py','contract.py',
        'realization.py','context009.py','runtime009.py','trace008.py','check009.py','worker.py',
        'relations011.py','prompts011.py','inference011.py','observe011.py','realization011.py','check011.py',
                    'relations012.py','prompts012.py','observe012.py','realization012.py','check012.py',
                    'observer013_contract.py','relations013.py','prompts013.py','observe013.py','inference013.py','reference013.py','report013.py',
                    'meaning014_contract.py','meaning014.py','prompts014.py','meaning014_reference.py']]
    hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in files}
    return {'version':'artifact-service009/1','profile':'typed008/1','target':'reaction_network',
        'input_format':'livingmath-artifact/1','kinds':['GUARDED_TRANSFORMATION','TEXTUAL_PROGRESSION','SIGNED_RESPONSE','STATE_TRANSITION'],
        'general_interpretation': {'opt_in': 'source.interpretation="general011"',
            'source_descriptor': 'source-relations011/1', 'observer': 'source-observer011/1',
            'backend_status': getattr(semantic_provider, 'assurance', 'MODEL_BACKEND_ASSURANCE_UNSPECIFIED')
                if semantic_provider is not None else 'NO_GENERAL_SEMANTIC_PROPOSER',
            'model': getattr(semantic_provider, 'model', None),
            'last_call_status': getattr(semantic_provider, 'last_status', 'NOT_CONFIGURED'),
            'provider_binding': getattr(semantic_provider, 'fingerprint', None),
            'max_model_calls_per_task': 8, 'model_call_wall_s': 120,
            'source_truth_verification': False},
        'observer_semantics': {'opt_in': 'source.interpretation="observer012"',
            'source_descriptor': 'source-relations012/1', 'source_graph': 'source-graph012/1',
            'observer': 'source-observer012/1', 'meta_only': True, 'target_model_optional': True,
            'source_verified': False, 'new_fundamental_operations': False},
        'observer_inference': {'opt_in': 'source.interpretation="observer013"', 'version': 'observer-inference013/1',
            'independent_finite_reference': True, 'world_verification': False, 'new_fundamental_operations': False},
        'meaning_pivot':{'opt_in':'source.interpretation="meaning014"','experimental':True,'A0_preserved':True,'primary_workflow':'B_PLUS','max_source_calls':3,'source_verified':False},
        'raw_input':True,'server_owned_compilation':True,'source_registration':'research_autonomy_ingest',
        'task_status':'research_autonomy_status','task_control':'research_autonomy_control',
        'history_export':'research_autonomy_history(view=export)','readable_report':'research_autonomy_history(view=report)',
        'limits':{'raw_UTF8_bytes':48000,'source_views':4,'worker_CPU_seconds':5,'worker_wall_seconds':6,
            'worker_AS_MiB':512,'worker_input_bytes':64000,'worker_output_bytes':256000,'species':8,'reactions':12,
            'guards':4,'markings':256,'task_workers_max':128,'task_models_max':64,'task_retries_max':3},
        'compiler_observer_hashes':hashes,'installed_profile_binding':digest(hashes),'backend_binding':backend_binding(),
        'reaction_SMT':'UNKNOWN_REACTION_SMT_NOT_IMPLEMENTED_USE_EXACT_FINITE',
        'source_semantics':'CONDITIONAL_NOT_VERIFIED','physical_realization':'NOT_ESTABLISHED'}
