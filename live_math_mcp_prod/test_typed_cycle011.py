"""011 contracts/atomicity/authority; only temporary QA databases and fresh sources."""
import asyncio
import copy
import json
from pathlib import Path
import sqlite3

import pytest
from pydantic import ValidationError
from normalizer import canonical, digest
from normalization_oracle import materialize
from native_preview008_qa import readonly_state
from qa_positive_acceptance import write_json
from research_store import ResearchStore
from research_engine010_qa import inspection, PRIOR009
from research_cycle009_worlds import declarations, environments, checksum
from research_cycle009 import requests
from typed_cycle011 import TypedCycle, journal_state, require_ledger_order
from typed_cycle011_contract import MeasurementEnvelope, ReceiptRequest
from typed_cycle011_operator import commit
from typed_cycle011_store import install, connect, TABLES, assert_isolated
from typed_cycle011_qa import Acceptance, sha


@pytest.mark.parametrize('index',range(6))
def test_legacy009_cannot_be_backfilled(index,tmp_path):
    case=inspection()[index];source=json.loads((PRIOR009/'source-snapshots'/(case['world']+'-step'+str(case['cycle_index'])+'-after.json')).read_text())
    db=tmp_path/'legacy.sqlite3';materialize(source,db);before=readonly_state(db)
    out=TypedCycle(db).validate(source['project'],case['move_id'],case['measurement_event_id'])
    assert out['status']=='INSUFFICIENT_MEASUREMENT_BINDING' and not out['execution_permission']['allowed']
    assert readonly_state(db)==before


def test_migration_refuses_same_database_and_preserves_schema5(tmp_path):
    db=tmp_path/'qa.sqlite3';ResearchStore(db);before=readonly_state(db)
    with pytest.raises(ValueError,match='PRODUCTION'):install(db,db)
    assert readonly_state(db)==before
    other=tmp_path/'other.sqlite3';ResearchStore(other);install(db,other)
    with sqlite3.connect(db) as c:
        assert c.execute('PRAGMA user_version').fetchone()[0]==5
        assert all(c.execute('SELECT 1 FROM sqlite_master WHERE name=?',(n,)).fetchone() for n in TABLES)


def test_private_server_and_writer_refuse_unmarked_production_database(tmp_path):
    from typed_cycle011_server import create_typed_server
    db=tmp_path/'unmarked.sqlite3';ResearchStore(db);before=readonly_state(db)
    with pytest.raises(ValueError,match='ISOLATED'):create_typed_server(db)
    with pytest.raises(ValueError,match='ISOLATED'),connect(db,True):pass
    assert readonly_state(db)==before


@pytest.mark.parametrize('action',['UPDATE','DELETE'])
def test_typed_append_only_and_readonly_authorizer(tmp_path,action):
    db=tmp_path/'qa.sqlite3';other=tmp_path/'other.sqlite3';ResearchStore(db);ResearchStore(other);install(db,other)
    with connect(db,True) as c:c.execute("INSERT INTO typed011_scopes VALUES ('LM_QA_TYPED011_UNIT','{}')")
    before=readonly_state(db)
    with pytest.raises(sqlite3.DatabaseError),connect(db,True) as c:
        c.execute("UPDATE typed011_scopes SET payload_json='bad'" if action=='UPDATE' else 'DELETE FROM typed011_scopes')
    with pytest.raises(sqlite3.DatabaseError),connect(db) as c:c.execute('DELETE FROM typed011_scopes')
    assert readonly_state(db)==before


@pytest.mark.parametrize('ids',[(2,1,3,4),(1,3,2,4),(1,2,4,3),(1,2,3,3)])
def test_measurement_order_is_strict_and_preactivation_event_cannot_pass(ids):
    with pytest.raises(ValueError,match='ORDER'):require_ledger_order(*ids)
    require_ledger_order(1,2,3,4)


@pytest.mark.parametrize('ordered',[False,True])
def test_real_MCP_new_measurement_and_atomic_receipt(tmp_path,ordered):
    db=tmp_path/'isolated.sqlite3';canonical_db=tmp_path/'canonical.sqlite3';ResearchStore(db);ResearchStore(canonical_db);install(db,canonical_db)
    w=declarations('UNIT011')[1 if ordered else 0];w['project']='LM_QA_TYPED011_UNIT'
    if ordered:
        a=w['parameters']['actions']
        w['tests']=[{'id':'ordered0','ordinal':0,'suffix':[a[3],a[4]],'cost':0},
                    {'id':'ordered1','ordinal':1,'suffix':[a[4],a[3]],'cost':4}]
    w.pop('scope');w.pop('fixture_sha256');w['fixture_sha256']=checksum(w);w['scope']='QA011/unit/'+w['fixture_sha256']
    env=environments([w],['fresh-unit-salt'])[0]
    for folder in ('world-inputs','sealed-environments'):(tmp_path/folder).mkdir()
    write_json(tmp_path/'world-inputs'/(w['id']+'.json'),w);write_json(tmp_path/'sealed-environments'/(w['id']+'.json'),env)
    runner=Acceptance(tmp_path,db,canonical_db)
    async def work():
        binding=await runner.seed(w,sha(tmp_path/'sealed-environments'/(w['id']+'.json')))
        record=await runner.precommit(w,binding,'unit')
        runner.activate(w,record,'unit');measured=runner.measure(w,record)
        engine=TypedCycle(db);before=readonly_state(db)
        validation=engine.validate(w['project'],record['move_id'],measured['event_id'])
        assert validation['status']=='VALID_BOUND_MEASUREMENT',validation
        assert readonly_state(db)==before
        env=measured['envelope']
        if ordered:
            bad=copy.deepcopy(env);bad['suffix'].reverse();bad['suffix_ordinals'].reverse()
            row=await runner.event(w,'reversed-ordered-suffix',{'measurement_binding':bad},kind='experiment',status='experiment')
            out=await runner.call('research_cycle_validate',{'project':w['project'],'move_id':record['move_id'],'event_id':row['id']})
            assert out['status']=='REJECTED' and out['reason']=='MEASUREMENT_BINDING_MISMATCH'
        for field in MeasurementEnvelope.model_fields:
            if not MeasurementEnvelope.model_fields[field].is_required():continue
            bad=copy.deepcopy(env);del bad[field]
            with pytest.raises(ValidationError):MeasurementEnvelope.model_validate(bad)
        for value in ('verified','prediction'):
            with pytest.raises(ValidationError):MeasurementEnvelope.model_validate({**env,'proof_status':value})
        request={'project':w['project'],'move_id':record['move_id'],'event_id':measured['event_id'],
            'request_key':'unit','outcome':env['outcome'],'observed':env['observed'],'summary':env['summary'],'reason':env['reason']}
        # Inject a journal INSERT fault: terminal status and receipt must roll back together.
        with connect(db,True) as c:c.execute("CREATE TRIGGER unit_abort_journal BEFORE INSERT ON typed011_journal BEGIN SELECT RAISE(ABORT,'unit injected fault'); END")
        before=readonly_state(db)
        with pytest.raises(sqlite3.IntegrityError,match='unit injected'):commit(db,request)
        assert readonly_state(db)==before
        with connect(db,True) as c:c.execute('DROP TRIGGER unit_abort_journal')
        receipt=commit(db,request);assert receipt['status']=='COMPLETED' and receipt['proof_status']=='unverified'
        before=readonly_state(db);assert commit(db,request)['idempotent'] and readonly_state(db)==before
        with pytest.raises(ValueError,match='CONFLICT'):commit(db,{**request,'reason':'tampered'})
        feedback=None
        if env['outcome']=='SUCCESS':
            feedback=await runner.event(w,'derived-success-exclusion',{'observation':{'test_id':env['test_id'],'readout':env['observed'],
                'scope':w['scope'],'version':1,'observer':w['observer']},'relations':[{'type':'derived_from','target_ref':'event:'+str(measured['event_id'])}]},
                kind='counterexample',status='experiment',parent=measured['event_id'])
        _,native=requests(db,w,binding,feedback['id'] if feedback else None)
        out=await runner.call('research_cycle_preview',{'request':native})
        assert out['status']=='NO_NEW_DISTINCTION_BOUNDED'
        with connect(db) as c:
            p=c.execute('SELECT payload_json FROM typed011_precommits WHERE id=?',(record['precommit_id'],)).fetchone()
            pc=json.loads(p[0]);assert journal_state(c,w['project'],w['scope'],pc['source_family_id'],pc['claim_fingerprint'],'0'*64)=='REQUIRES_REVIEW'
        with pytest.raises(ValidationError):ReceiptRequest.model_validate({**request,'proof_status':'verified'})
        assert ResearchStore(db).verify_audit()['ok']
    asyncio.run(runner.session('unit',work))
