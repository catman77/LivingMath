"""014 preregistration only. Never imported by learner, selector or MCP engine."""
POLICY={
    'version':'014.P0.1','discovery_prefix_length':2,'separate_validation_words':[[0,1,0,0]],
    'validation_domain':[[0,1,0,1],[1,0,1,0]],'random_seed':140027,
    'score':['unseen guarded only','new ordered adjacent pairs descending','composition length descending','cost ascending','ordinal ascending'],
    'max_completed_steps':{'A':3,'B':2,'C':0,'D':0},
    'hidden_targets':{'A':[0,1],'B':[]},
    'budgets':{'native_queries_per_world':20000,'native_queries_per_tool':2048,'P0_wall_s':120,'P0_CPU_s':90,'RSS_KiB':524288},
    'side_effects':{'engine':['private precommit/proposal/audit append'],'operator':['scoped activation','atomic receipt/journal commit','QA closure'],
                                                                    'executor':['fresh post-activation native measurement/event/artifact'],'oracle':['post-measurement independent evaluation only']},
    'expected_classes':{'A':'bounded stable law; singleton still permits two new law probes',
                                                                                    'B':'candidate agrees locally but clock-dependent native generator refutes extrapolation; requires review',
                                                                                    'C':'law only inside explicit length≤2 research guard; longer probes refused',
                                                                                    'D':'same image with different successor and separate opaque inspection control; no grant'},
    'failure':'unexpected guarded-prediction error stops claim; expected B falsification stops B and cannot be repaired from hidden truth',
    'production_deploy':False,'LLM_P1':False,'oracle_access_by_engine':'OS denied via Landlock; fail closed if unavailable'}


def declarations():
    return [
        {'id':'A','algebra':'affine','initial':[1,0],'arity':2,'guard_width':4,'clock_period':0,'discrimination_histories':[[],[0],[1],[0,0],[0,1],[1,1]]},
        {'id':'B','algebra':'permutation','initial':[0,1,2,3],'arity':2,'guard_width':4,'clock_period':4,'discrimination_histories':[[],[0]]},
        {'id':'C','algebra':'stack','initial':[],'arity':3,'guard_width':2,'clock_period':0,'discrimination_histories':[[],[0]]},
        {'id':'D','algebra':'latch','initial':[0,0],'arity':2,'guard_width':4,'clock_period':0,'discrimination_histories':[[],[1]]},
    ]
