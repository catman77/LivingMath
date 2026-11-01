"""DAV integration regression tests; all stores and experiments are local QA."""
import asyncio
import random
import sqlite3

import pytest

from davcore.ast import Formula, eq, implication
from davcore.adapters import Adapter, AdapterSpec
from davcore.finite import check, audit, library
from davcore.models import Budget


def adapter(kind='ca', **kwargs):
    return Adapter(AdapterSpec(kind=kind, **kwargs))


def test_two_domain_goldens():
    ca = adapter()
    assert check(ca, implication('R0', 'R2', 'T0', 'T2'))['status'] == 'proved'
    bad = check(ca, implication('T0', 'T1', 'T0', 'T2'))
    assert bad['status'] == 'refuted' and bad['counterexample']['steps']
    assert check(adapter('graph'), implication('S0', 'S2', 'P', 'Q'))['status'] == 'proved'


def test_no_caller_completeness_and_no_observation_promotion():
    a = adapter()
    assert check(a, implication('R0', 'R2', 'T0', 'T2'), states=[0, 255])['status'] == 'consistent_with_observations'
    empirical = adapter(fidelity='empirical')
    assert check(empirical, implication('R0', 'R2', 'T0', 'T2'))['status'] == 'consistent_with_observations'
    with pytest.raises(ValueError):
        check(adapter(mask=15), implication('R0', 'R2', 'T0', 'T2'))
    assert check(adapter(mask=15), implication('R0', 'R2', 'T0', 'T2', equality='observation'))['scope']['equality'] == 'observation'


def test_projection_witness_uses_actual_paired_states():
    a = adapter(mask=15)
    result = audit(a)
    assert not result['congruent']
    w = result['congruence_witness']
    x, y = w['states']
    assert a.observe(x) == a.observe(y)
    assert a.observe(a.apply(w['operation'], x)) != a.observe(a.apply(w['operation'], y))


def test_typed_ast_and_budget():
    with pytest.raises(ValueError):
        Formula.model_validate({'body': {'tag': 'eq', 'left': {'tag': 'var', 'name': 'y'}, 'right': {'tag': 'var', 'name': 'x'}}})
    with pytest.raises(ValueError):
        check(adapter(), eq('MISSING', 'R0'))
    out = check(adapter(), eq('T0', 'T1'), budget=Budget(max_operations=1))
    assert out['status'] == 'timeout' and out['metrics']['operation_applications'] <= 1


def test_reduction_sound_and_explicit_relations():
    for a in [adapter(), adapter('graph')]:
        out = library(a)
        assert out['status'] == 'proved' and out['count'] > 0
        assert out['relations']
        for f in out['laws']:
            assert check(a, Formula.model_validate(f))['status'] == 'proved'


def test_held_out_width_and_composition():
    a = adapter(width=5)
    f = Formula.model_validate({'body': {'tag': 'eq', 'left': {'tag':'apply','operation':'R2','argument': {'tag':'apply','operation':'R3','argument':{'tag':'var','name':'x'}}}, 'right': {'tag':'var','name':'x'}}})
    assert check(a, f)['status'] == 'proved'


def test_baseline_unsound_complete_flag_is_not_in_api():
    import inspect
    assert 'complete' not in inspect.signature(check).parameters
    with pytest.raises(ValueError):
        AdapterSpec.model_validate({'kind':'ca','python':'import os'})

@pytest.mark.parametrize('kind,width', [('ca',3),('ca',5),('ca',8),('graph',8),('gate6',8)])
def test_direct_smt_differential(kind, width):
    pytest.importorskip('z3')
    from davcore.smt import check_smt
    a = adapter(kind, width=width)
    rng = random.Random(7301)
    formulas = [eq(a.ops[0], a.ops[-1])]
    formulas += [implication(*(rng.choice(a.ops) for _ in range(4))) for _ in range(16)]
    for f in formulas:
        finite, smt = check(a, f), check_smt(a, f)
        assert finite['status'] == smt['status'], (a.spec, f, finite, smt)
        if smt['status'] == 'refuted':
            assert not smt['counterexample']['actual_relation']


def test_smt_operation_translation_against_every_finite_input():
    z3 = pytest.importorskip('z3')
    from davcore.smt import translate_operation
    for a in [adapter(width=3), adapter(width=5), adapter('graph'), adapter('gate6')]:
        for op in a.ops:
            x = z3.BitVec('x', a.width)
            translated = translate_operation(z3, a, op, x)
            for state in a.states():
                value = z3.simplify(z3.substitute(translated, (x, z3.BitVecVal(state, a.width)))).as_long()
                assert value == a.apply(op, state), (a.spec, op, state)


def test_scope_condition_explicit_for_gate6():
    f = implication('P', 'One', 'Joint', 'One')
    original = check(adapter('gate6'), f)
    assert original['status'] == 'refuted' and original['counterexample']['state'] == 1
    conditional = check(adapter('gate6', assumption='P_implies_Q_NOT_SOURCE_ATTESTED'), f)
    assert conditional['status'] == 'proved'
    assert conditional['scope']['adapter']['assumptions'] == ['P_implies_Q_NOT_SOURCE_ATTESTED']
    assert original['execution_permission'] == conditional['execution_permission'] == {'allowed':False}


def test_observation_library_never_promoted_and_paging():
    from davcore.finite import candidates
    a = adapter('graph')
    assert library(a, states=[0,255])['status'] == 'consistent_with_observations'
    first = candidates(a, Budget(max_candidates=7))
    second = candidates(a, Budget(max_candidates=7), first['next_cursor'])
    assert first['laws'] != second['laws']
    assert not first['search_complete']
    all_laws = candidates(a, Budget(max_candidates=1000))
    assert all_laws['search_complete'] and len(all_laws['laws']) == 90


def test_storage_append_only_isolation_idempotency(tmp_path):
    from davcore.storage import Store
    s = Store(tmp_path/'dav.sqlite3')
    r = s.append('A','evidence','key',{'law':1},{'status':'refuted','counterexample':1})
    assert s.append('A','evidence','key',{'law':1},{'status':'proved'})['id'] == r['id']
    with pytest.raises(ValueError, match='CONFLICT'):
        s.append('A','evidence','key',{'law':2},{})
    with pytest.raises(ValueError, match='FOREIGN'):
        s.get('B',r['id'])
    with s.connect() as c:
        with pytest.raises(sqlite3.IntegrityError,match='APPEND_ONLY'):
            c.execute("UPDATE dav_records SET payload_json='{}'")
        with pytest.raises(sqlite3.IntegrityError,match='APPEND_ONLY'):
            c.execute('DELETE FROM dav_records')
    assert s.integrity()['ok']
    with s.connect() as c:
        c.execute('DROP TRIGGER dav_no_update')
        c.execute("UPDATE dav_records SET payload_json='{}'")
    assert not s.integrity()['ok']


def test_real_process_persistence_no_default_write_and_stale_binding(tmp_path):
    from davcore.service import Service
    async def run():
        s = Service(tmp_path/'dav.sqlite3')
        r = await s.register('A',AdapterSpec(kind='graph'),'register')
        assert (await s.register('A',AdapterSpec(kind='graph'),'register'))['id'] == r['id']
        args = {'formula':implication('S0','S2','P','Q'),'expected_binding':r['payload']['binding']}
        out = await s.compute('A',r['id'],'check',**args)
        assert out['status'] == 'proved' and s.store.integrity()['rows'] == 1
        ev = await s.compute('A',r['id'],'check',persist=True,request_key='law',**args)
        ev2 = await s.compute('A',r['id'],'check',persist=True,request_key='law',**args)
        assert ev['id'] == ev2['id'] and s.export('A',ev['id'])['certificate_current']
        with pytest.raises(ValueError):
            await s.compute('B',r['id'],'check',**args)
        with pytest.raises(ValueError):
            await s.compute('A',r['id'],'check',formula=eq('P','Q'),expected_binding='0'*64)
        with pytest.raises(ValueError,match='CONFLICT'):
            await s.compute('A',r['id'],'check',formula=eq('P','Q'),expected_binding=r['payload']['binding'],persist=True,request_key='law')
        assert s.store.integrity()['ok']
    asyncio.run(run())


def test_feature_flag_default_and_outer_schema(tmp_path,monkeypatch):
    from mcp_server import create_server
    from research_store import ResearchStore
    monkeypatch.delenv('LIVE_MATH_DAV',raising=False)
    old = create_server(ResearchStore(tmp_path/'research.sqlite3'))
    assert len(old._tool_manager.list_tools()) == 18
    assert old._tool_manager.get_tool('dav_check_law') is None
    monkeypatch.setenv('LIVE_MATH_DAV','1')
    monkeypatch.setenv('LIVE_MATH_DAV_DB',str(tmp_path/'dav.sqlite3'))
    new = create_server(ResearchStore(tmp_path/'research.sqlite3'))
    assert len(new._tool_manager.list_tools()) == 26
    for name in ['dav_check_law','dav_observe','dav_register_adapter']:
        schema = new._tool_manager.get_tool(name).parameters
        assert schema['additionalProperties'] is False
    for tool in old._tool_manager.list_tools():
        assert new._tool_manager.get_tool(tool.name).parameters == tool.parameters


def test_database_alias_and_non_dav_rejected(tmp_path):
    from davcore.service import Service
    from research_store import ResearchStore
    p = tmp_path/'research.sqlite3'
    ResearchStore(p)
    with pytest.raises(ValueError,match='ISOLATED'):
        Service(p,(p,))
    link = tmp_path/'link.sqlite3'
    link.hardlink_to(p)
    with pytest.raises(ValueError,match='ISOLATED'):
        Service(link,(p,))
    with pytest.raises(ValueError,match='OWN_DATABASE'):
        Service(p)


def test_hard_deadline_and_cancellation_leave_no_worker(tmp_path):
    from davcore.service import Service
    async def run():
        s=Service(tmp_path/'dav.sqlite3')
        r=await s.register('A',AdapterSpec(kind='ca'),'r')
        args={'expected_binding':r['payload']['binding']}
        task=asyncio.create_task(s.compute('A',r['id'],'reduce',**args))
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        assert not s.boundary.running
        out=await s.compute('A',r['id'],'reduce',budget=Budget(deadline_ms=1),**args)
        assert out['status']=='timeout'
        assert not s.boundary.running
    asyncio.run(run())


def test_worker_cannot_read_file_or_open_network():
    import subprocess,sys
    code = "from davcore.worker import restrict; restrict(); open('/etc/passwd').read()"
    r=subprocess.run([sys.executable,'-B','-c',code],text=True,capture_output=True)
    assert r.returncode!=0 and 'DAV_WORKER_IO_DENIED:open' in r.stderr
    code = 'import socket; from davcore.worker import restrict; restrict(); socket.socket()'
    r=subprocess.run([sys.executable,'-B','-c',code],text=True,capture_output=True)
    assert r.returncode!=0 and 'DAV_WORKER_IO_DENIED:socket.' in r.stderr


def test_invalid_adapter_class_rejected():
    class Faulty(Adapter):
        def apply(self,op,state):return 0
    a=Faulty(AdapterSpec(kind='ca'))
    assert audit(a)['status']=='invalid_adapter'
    with pytest.raises(ValueError,match='UNREGISTERED'):
        check(a,eq('T0','T1'))


def test_empty_samples_and_small_limits_are_not_proofs():
    a=adapter()
    assert check(a,eq('T0','T0'),states=[])['status']=='unknown'
    assert check(a,eq('T0','T0'),budget=Budget(max_states=1))['status']=='timeout'
    with pytest.raises(ValueError):check(a,eq('T0','T0'),states=[0,0])
    with pytest.raises(ValueError):check(a,eq('T0','T0'),states=[True])


def test_ast_is_immutable_and_composition_depth_bounded():
    from davcore.ast import Var, Apply
    f=eq('R0','R1')
    with pytest.raises(ValueError):f.equality='observation'
    t=Var()
    for _ in range(15):t=Apply(operation='R0',argument=t)
    with pytest.raises(ValueError,match='DEPTH'):
        Formula(body={'tag':'eq','left':t.model_dump(),'right':Var().model_dump()})
    assert eq('R0','R1').canonical_ast()==eq('R1','R0').canonical_ast()


@pytest.mark.parametrize('reason,expected',[('incomplete theory','unknown'),('timeout','timeout')])
def test_smt_undecided_is_preserved(monkeypatch,reason,expected):
    z3=pytest.importorskip('z3')
    from davcore.smt import check_smt
    class Undecided:
        def set(self,**kw):pass
        def add(self,*args):pass
        def check(self):return z3.unknown
        def reason_unknown(self):return reason
    monkeypatch.setattr(z3,'Solver',Undecided)
    assert check_smt(adapter(),eq('R0','R1'))['status']==expected


def test_smt_absence_and_empirical_domain_do_not_create_proof(monkeypatch):
    import sys
    from davcore.smt import check_smt
    monkeypatch.setitem(sys.modules,'z3',None)
    assert check_smt(adapter(),eq('R0','R1'))['status']=='unknown'
    assert check_smt(adapter(fidelity='empirical'),eq('R0','R0'))['status']=='unknown'


def test_optional_explorer_is_suggestion_only():
    from davcore.explorer import ProbeContext,probes
    c=ProbeContext('a'*64,(0,1,2,3),2,3)
    assert probes(c)==probes(c)
    assert probes(c)['neural_W_status'].startswith('NOT_RUN')
    class Bad:
        def suggest(self,context):return (0,999)
    with pytest.raises(ValueError):probes(c,Bad())


def test_backend_change_invalidates_saved_certificate(tmp_path,monkeypatch):
    from davcore.service import Service
    async def run():
        s=Service(tmp_path/'dav.sqlite3')
        r=await s.register('A',AdapterSpec(kind='graph'),'r')
        ev=await s.compute('A',r['id'],'check',formula=eq('P','P'),expected_binding=r['payload']['binding'],persist=True,request_key='check')
        monkeypatch.setattr('davcore.service.backend_binding',lambda:'b'*64)
        exported=s.export('A',ev['id'])
        assert not exported['certificate_current'] and exported['effective_status']=='unknown'
        assert exported['record']['payload']['status']=='proved'
    asyncio.run(run())


def test_future_storage_schema_is_not_downgraded(tmp_path):
    from davcore.storage import Store
    p=tmp_path/'future.sqlite3'
    with sqlite3.connect(p) as c:c.execute('PRAGMA user_version=2')
    with pytest.raises(ValueError,match='NEWER'):
        Store(p)
    with sqlite3.connect(p) as c:assert c.execute('PRAGMA user_version').fetchone()[0]==2
