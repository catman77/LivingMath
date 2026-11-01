"""Conditional observer consequences: never source/world verification."""
from copy import deepcopy

import pytest


def value(v=None, status=None):
    return {'status': status or ('KNOWN' if v is not None else 'UNKNOWN'), 'value': v, 'conflicts': [],
        'addresses': [] if v is None else [{'ref':'qa:1','quote_sha256':'a'*64,'byte_ranges':[[0,1]],'ambiguous_occurrence':False}]}


def profile(name, features, left, right, *, scope='T', time='T', referent='pair'):
    return {'id':name,'owner':name,'features':features,'criterion':'SET','source_status':'HYPOTHESIS','addresses':[],
        'samples':[{'state_key':s,'values':{f:vals.get(f,value()) for f in features},
            'scope':scope,'time':time,'referent':referent,'binding_addresses':[{'ref':'qa:1'}]} for s,vals in [('A',left),('B',right)]]}


def model(profiles, reports=()):
    return {'compiled_hash':'b'*64,'source_hashes':['c'*64], 'observer':{'inference':{
        'version':'observer-inference013/1','profiles':profiles,'reports':list(reports),'source_sha256':'c'*64}}}


def infer(m, **kw):
    from semantic_repair.inference013 import analyze
    return analyze(m, **kw)


def test_known_equal_color_different_mass_not_identity():
    m=model([profile('C',['color'],{'color':value('red')},{'color':value('red')}),
        profile('M',['mass'],{'mass':value('2')},{'mass':value('3')})])
    r=infer(m);eq={q['observers'][0]:q for q in r['consequences'] if q['kind']=='OBSERVATIONAL_EQUALITY'}
    assert eq['C']['verdict']=='ENTAILED_UNDER_ASSUMPTIONS'
    assert eq['M']['verdict']=='REFUTED_UNDER_ASSUMPTIONS'
    assert eq['M']['counterexample'] and not r['source_verified'] and not r['full_state_identity_inferred']
    assert r['independent_enumeration_agrees']


def test_unknown_and_negative_are_not_values_or_false():
    m=model([profile('C',['color'],{}, {'color':value('red')})])
    q=next(q for q in infer(m)['consequences'] if q['kind']=='OBSERVATIONAL_EQUALITY')
    assert q['verdict']=='UNKNOWN_INSUFFICIENT_OBSERVATION'
    assert q['witness'] and q['counterexample'] and len(q['missing_observations'])==1
    m['observer']['inference']['profiles'][0]['samples'][0]['values']['color']=value('red','EXPLICIT_NEGATIVE')
    q=next(q for q in infer(m)['consequences'] if q['kind']=='OBSERVATIONAL_EQUALITY')
    assert q['verdict']=='REFUTED_UNDER_ASSUMPTIONS'


def test_same_projection_implication_is_nonvacuous_and_ablatable():
    m=model([profile('C',['color','mass'],{},{}),profile('D',['color'],{},{})])
    r=infer(m);q=next(q for q in r['consequences'] if q['kind']=='PROJECTION_IMPLICATION' and q['observers']==['C','D'])
    assert q['verdict']=='ENTAILED_UNDER_ASSUMPTIONS' and q['nonvacuous_premise']
    assert q['essential_basis_ablations'] and all(x['counterexample'] for x in q['essential_basis_ablations'])
    assert q['dav_formula']['dsl_version']=='dav-equations/1'


def test_disjoint_unknown_features_never_entail_equality():
    r=infer(model([profile('C',['color'],{},{}),profile('M',['mass'],{},{})]))
    assert not any(q['verdict']=='ENTAILED_UNDER_ASSUMPTIONS' for q in r['consequences'])


def test_conflict_does_not_explode():
    v=value();v.update(status='CONFLICT',conflicts=[{'value':'red','negative':False,'addresses':[{'ref':'qa:1'}]},
        {'value':'blue','negative':False,'addresses':[{'ref':'qa:2'}]}])
    r=infer(model([profile('C',['color'],{'color':v},{'color':value('red')})]))
    assert all(q['verdict']=='CONFLICTING_REPORTS' for q in r['consequences'])


def test_scope_time_and_referent_mismatch_remain_unknown():
    for key in ['scope','time','referent']:
        m=model([profile('C',['color'],{'color':value('red')},{'color':value('red')})])
        m['observer']['inference']['profiles'][0]['samples'][1][key]=None if key=='referent' else 'different'
        q=infer(m)['consequences'][0]
        assert q['verdict']=='UNKNOWN_INSUFFICIENT_OBSERVATION' and q['missing_bindings']


def test_reports_only_common_meaning_is_explicit_and_removable():
    reports=[{'id':'r1','observer_id':'a','speaker':'First','source':'A','target':'B','comparison':'EQUALITY','reported_value':'TRUE','scope':None,'time':None,'addresses':[{'ref':'qa:1'}]},
        {'id':'r2','observer_id':'b','speaker':'Second','source':'A','target':'B','comparison':'RETURN','reported_value':'FALSE','scope':None,'time':None,'addresses':[{'ref':'qa:2'}]}]
    r=infer(model([],reports))
    qs=[q for q in r['consequences'] if q['kind']=='REPORT_COMPATIBILITY']
    assert {q['verdict'] for q in qs}=={'ASSERTED_BY_SOURCE_ONLY','CONFLICTING_REPORTS'}
    q=next(q for q in qs if q['verdict']=='CONFLICTING_REPORTS')
    assert q['assumptions'] and q['counterexample_without_assumption']
    assert all(q['world_truth']=='UNKNOWN' for q in qs)


def test_no_vacuous_or_resource_false_pass():
    m=model([profile('C',['a','b','c','d'],{},{}),profile('D',['a','b','c','d'],{},{})])
    r=infer(m,max_worlds=2)
    assert any(q['verdict']=='RESOURCE_BOUND' for q in r['consequences'])
    assert not any(q['verdict']=='ENTAILED_UNDER_ASSUMPTIONS' for q in r['consequences'])


def annotation013(packet):
    from semantic_repair.inference011 import canonical_packet
    from test_observer_semantics012 import annotation
    p,r=annotation(packet);p['version']='source-relations013/1';r['version']='source-critic013/1';r['observations']=[]
    spans=canonical_packet(packet)[0]['spans']
    def citation(quote):return next({'ref':s['id'],'quote':quote} for s in spans if quote in s['text'])
    h=p['readings'][0]
    for e in h['relations']:
        e.update(kind='REPEAT',order_kind='TEXT_ORDER',interpretation_assumptions=['SCOPED_SOURCE_READING'])
        e['source_claim'].update(comparison='EQUALITY',reported_value='TRUE',comparison_scope='samples',comparison_time='session')
    for name,feature,vals in [('C','color',['red','red']),('M','mass',['2','3'])]:
        evidence=[citation('session')]
        h['observers'].append({'id':name,'owner':name,'features':[feature],'criterion':'SET','evidence':evidence,
            'samples':[{'state_id':state,'values':[{'feature':feature,'status':'KNOWN','value':v,'evidence':[citation(v)],'conflicts':[]}],
                'scope':'samples','time':'session','referent':'pair A/B','binding_evidence':evidence} for state,v in zip(['A','B'],vals)]})
        r['observations'].append({'reading_id':h['id'],'observer_id':name,'status':'HYPOTHESIS','explicit_values_checked':True,
            'binding_time_scope_checked':True,'evidence':evidence,'reason':'Unit annotation of exact supplied values and common session, no source oracle.'})
    return p,r


def raw013():
    from test_general_interpretation011 import raw
    return raw('State A becomes B. A red mass 2, session for pair A/B samples.\nState B becomes A. B red mass 3, session for pair A/B samples.\n',interpretation='observer013')


def prepare013(tmp_path,mutate=None):
    from davcore.service import Service
    from research_automation.controller import Controller
    from semantic_repair.context009 import resolve,packets
    from semantic_repair.observe013 import align
    from semantic_repair.runtime009 import assemble
    from semantic_repair.compiler import compile_model
    c=Controller(Service(tmp_path/'dav.sqlite3'));receipt=c.ingest('QA013',raw013(),'source')
    ctx=resolve(c.service.store,'QA013',receipt['source_snapshot']['id']);packet=packets(ctx)[0][0]
    p,r=annotation013(packet)
    if mutate:mutate(p,r)
    obs=align(packet,p,r);item=assemble([obs],'QA013')['plans'][0]
    m=compile_model(item['premises'],item['binding'],profile='typed008/1',context=ctx)
    return c,ctx,item,m


def test_raw013_alignment_compilation_and_real_isolated_worker(tmp_path):
    import asyncio
    from semantic_repair.worker import call
    async def run():
        _,ctx,item,m=prepare013(tmp_path)
        assert m['observer_version']=='source-observer013/1'
        payload={k:item[k] for k in ['premises','binding']};payload['profile']='typed008/1'
        compiled=await call('artifact_compile',payload,context=ctx)
        assert compiled.pop('isolation')['probes']=={'file':'DENIED','socket':'DENIED'}
        assert compiled==m
        checked=await call('artifact_check',{**payload,'model':m},context=ctx)
        a=checked['analysis']['conditional_observer_inference']
        eq={q['observers'][0].split(':')[-1]:q['verdict'] for q in a['consequences'] if q['kind']=='OBSERVATIONAL_EQUALITY'}
        assert eq=={'C':'ENTAILED_UNDER_ASSUMPTIONS','M':'REFUTED_UNDER_ASSUMPTIONS'}
        assert checked['analysis']['traces']==[] and not a['source_verified'] and not a['execution_permission']['allowed']
    asyncio.run(run())


def test_013_controller_restart_report_export_dedup_and_foreign_stale(tmp_path):
    import asyncio
    from davcore.ast import digest
    from davcore.service import Service
    from research_automation.controller import Controller
    from research_automation import artifact
    from test_general_interpretation011 import settle
    class Provider:
        fingerprint=digest('annotation013-unit');assurance='UNIT_NOT_LLM';model='unit'
        async def infer(self,role,packet,proposals=None,feedback=None):
            p,r=annotation013(packet)
            return {'status':'OK','output':r if role=='critic013' else p,'usage':None}
    async def run():
        c=Controller(Service(tmp_path/'dav.sqlite3'),semantic_provider=Provider())
        first=c.ingest('QA013',raw013(),'same');assert c.ingest('QA013',raw013(),'same')==first
        c=Controller(Service(tmp_path/'dav.sqlite3'),semantic_provider=Provider());state=await settle(c,'QA013')
        assert state['status']=='COMPLETED',state
        rows=c.journal.rows(('artifact_result',),'QA013',case_id=first['case_ids'][0]);assert rows
        row=rows[0]
        assert artifact.certificate_current(c,'QA013',row)
        report=artifact.report(c,'QA013',first['case_ids'][0]);assert 'Условные' in report['report_ru']
        assert 'Условные' in artifact.report(c,'QA013',first['case_ids'][0],max_bytes=4096)['report_ru']
        with pytest.raises(ValueError,match='MISSING_OR_FOREIGN'):
            c.service.store.get('FOREIGN',row['id'])
        assert c.service.store.integrity()['ok']
        checked=row['payload']['check'];assert not checked['source_claim_verified']
        # A mutated target/source binding cannot borrow an old certificate.
        bad=deepcopy(row);bad['payload']['model']['observer']['inference']['source_sha256']='0'*64
        assert not artifact.certificate_current(c,'QA013',bad)
    asyncio.run(run())


def test_addressed_conflicting_values_survive_critic_conflict_status(tmp_path):
    def mutate(p,r):
        v=p['readings'][0]['observers'][0]['samples'][0]['values'][0]
        v.update(status='CONFLICT',value=None,conflicts=[{'value':'red','negative':False,'evidence':v['evidence']},
            {'value':'red','negative':True,'evidence':v['evidence']}])
        r['observations'][0]['status']='CONFLICT'
    _,_,_,m=prepare013(tmp_path,mutate)
    qs=infer(m)['consequences']
    assert any(q['verdict']=='CONFLICTING_REPORTS' for q in qs)
    assert m['observer']['inference']['profiles'][0]['samples'][0]['values']['color']['status']=='CONFLICT'


def test_independent_enumerator_disagreement_is_an_error(monkeypatch):
    from semantic_repair import inference013
    monkeypatch.setattr(inference013,'enumerate_reference',lambda plan,limit:{'status':'COMPLETE','world_count':1,'rows':[]})
    with pytest.raises(ValueError,match='INDEPENDENT_ENUMERATOR_DISAGREEMENT'):
        infer(model([profile('C',['c'],{'c':value('red')},{'c':value('red')})]))


def test_dav_truth_vector_disagreement_is_an_error(monkeypatch):
    from semantic_repair import inference013
    monkeypatch.setattr(inference013,'witness',lambda *a:{'actual_relation':False})
    with pytest.raises(ValueError,match='DAV_VECTOR_DISAGREEMENT'):
        infer(model([profile('C',['c'],{'c':value('red')},{'c':value('red')})]))


def test_unknown_minimum_needs_both_coordinates_and_no_world_claim():
    q=infer(model([profile('C',['c'],{},{})]))['consequences'][0]
    assert len(q['missing_observations'])==2
    assert q['world_truth']=='UNKNOWN' and not q['source_verified']


def test_inconsistent_shared_adoptions_no_vacuous_entailment():
    ps=[profile('C',['color'],{'color':value('red')},{'color':value('red')}),
        profile('D',['color'],{'color':value('blue')},{'color':value('blue')})]
    qs=infer(model(ps))['consequences']
    assert all(q['verdict']=='INCONSISTENT_ASSUMPTIONS' for q in qs if q['kind']=='PROJECTION_IMPLICATION')
    assert all(not q['nonvacuous_premise'] for q in qs if q['kind']=='PROJECTION_IMPLICATION')


def test_distinct_samples_are_comparable_without_full_identity():
    p=profile('C',['color'],{'color':value('red')},{'color':value('red')})
    p['criterion']='PARTIAL_SET'
    for s in p['samples']:s['referent']='sample '+s['state_key']
    q=infer(model([p]))['consequences'][0]
    assert q['verdict']=='ENTAILED_UNDER_ASSUMPTIONS'
    assert not q['full_state_identity_inferred']


def test_cross_observer_bindings_match_per_sample_not_across_samples():
    ps=[profile('C',['color','shape'],{},{}),profile('D',['color'],{},{})]
    for p in ps:
        for s in p['samples']:s['referent']='sample '+s['state_key']
    q=next(q for q in infer(model(ps))['consequences'] if q['kind']=='PROJECTION_IMPLICATION' and q['observers']==['C','D'])
    assert q['verdict']=='ENTAILED_UNDER_ASSUMPTIONS'
    ps[1]['samples'][0]['referent']='unresolved pronoun'
    q=next(q for q in infer(model(ps))['consequences'] if q['kind']=='PROJECTION_IMPLICATION' and q['observers']==['C','D'])
    assert q['verdict']=='UNKNOWN_INSUFFICIENT_OBSERVATION'


def test_bound_ablation_is_unresolved_never_declared_nonessential():
    q=infer(model([profile('C',['c'],{'c':value('red')},{'c':value('red')})]),max_worlds=1)['consequences'][0]
    assert q['necessity_check_status']=='RESOURCE_BOUND'
    assert q['unresolved_basis_ablations']
    assert not q['nonessential_basis_ablations']
