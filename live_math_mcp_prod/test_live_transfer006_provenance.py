import copy,json
from pathlib import Path
from live_transfer006_worlds import create_world,frame
from live_transfer006 import attend
from live_transfer006_source import load_frame
from normalizer import read_history,normalize_context
from research_store import ResearchStore


def test_feedback_receipt_hash_is_in_explicit_source_provenance(tmp_path):
    w=create_world(tmp_path/'world.sqlite3',0);f=frame(w);chosen=attend(f)
    port=f.port();state=port.load(f.words[w['refs']['h0']]);flags=[]
    for a in chosen['suffix']:
        ok=port.admissible(state,a);flags.append(ok);assert ok;state=port.extend(state,a)
    receipt={'scope':w['query']['scope'],'version':1,'observer':f.spec['observer'],'test_id':chosen['test_id'],
             'readout':{'defined':True,'observation':port.observe(state,f.spec['observer']),'admissibility':flags}}
    event=ResearchStore(Path(w['database'])).record(w['query']['project'],'counterexample','Finite feedback',json.dumps({'observation':receipt}),'experiment')
    q=copy.deepcopy(w['query']);q['move']['parent_event_ids'].append(event['id'])
    h=read_history(Path(w['database']),w['query']['project']);f=load_frame(normalize_context(h,'finite',[q],'C2'),h,q)
    out=attend(f,'event:'+str(event['id']))
    assert event['id'] in out['source_event_ids']
    assert any(r['ref']=='event:'+str(event['id']) for r in out['known_failures'])
