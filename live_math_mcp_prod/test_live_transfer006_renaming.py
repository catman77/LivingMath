import copy,json
from live_transfer006_worlds import create_world,frame
from live_transfer006_qa import reframe
from live_transfer006 import interpret
from live_transfer006_oracle import pairs


def test_bijective_primitive_label_rename_does_not_create_new_distinction(tmp_path):
    w=create_world(tmp_path/'world.sqlite3',1);f=frame(w)
    pair=next(x for x in pairs(w['history'],w['query']) if x['hidden'])
    original=interpret(f,pair['left'],pair['right'])
    h=copy.deepcopy(w['history']);rename={a:'display_'+a for a in f.spec['parameters']['actions']}
    for row in h['tables']['events']:
        p=json.loads(row['content'])
        if 'word' in p:p['word']=[rename[a] for a in p['word']]
        if 'source_spec' in p:
            spec=p['source_spec'];spec['parameters']['actions']=[rename[a] for a in spec['parameters']['actions']]
            for t in spec['tests']:t['suffix']=[rename[a] for a in t['suffix']]
        row['content']=json.dumps(p)
    new=interpret(reframe(w,h),pair['left'],pair['right'],known=(original['fingerprint'],))
    assert new['status']=='NO_NEW_DISTINCTION',new
