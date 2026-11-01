from experiments import arithmetic,boa,step,read_rule,project_gate

def test_arithmetic_counterexample():
    _,a=arithmetic();w=a['witness'];assert sum(w['lhs'])==sum(w['rhs'])
    assert w['results'][0]!=w['results'][1]

def test_boa_exhaustive_counts():
    _,b=boa();assert b['attention_changes_next_count']>0
    assert b['mixed_fate_count']>0
    assert b['rotation_check_0x66']['equivariant']

def test_limits():
    assert project_gate('RH')['status']=='UNTESTED'
    assert project_gate('Soft_FTL')['status']=='UNTESTED'

def test_rule_zero():
    assert step(0,0)==0
    assert read_rule(0,0)==0
