"""Four native primary families plus frozen renamed/constants-changed holdouts."""
from itertools import product
import json
from pathlib import Path
from unittest.mock import patch

from live_transfer006_primitives import Port,State,native_observe,primitive_fingerprint
from live_transfer006_source import load_frame
from normalizer import normalize_context,read_history
from research_store import ResearchStore

SEED=106006
FAMILIES=['register','rewrite','permutation','history']


def create_world(path: Path, index: int) -> dict:
    family=FAMILIES[index%4];hidden=index>=4
    actions=[f'op{SEED+index}_{i}' for i in range((7 if hidden else 5) if family=='register' else 4 if family=='history' else 3)]
    p={'family':family,'actions':actions}
    if family=='register':p.update(initial=[0,1],modulus=7 if hidden else 5)
    if family=='rewrite':p.update(initial=['r','q','r'] if hidden else ['a','b','a'],letters=['r','q'] if hidden else ['a','b'],max_word=5 if hidden else 6)
    if family=='permutation':
        n=4 if hidden else 3;p.update(initial=list(range(n)),permutations=[[1,0]+list(range(2,n)),list(range(1,n))+[0],list(range(n))])
    if family=='history':p.update(initial=0,capacity=3 if hidden else 2,display_mod=3 if hidden else 2)
    words=[[2,2],[1,2,2],[2,2,2],[1,1],[3],[0,3],[],[1],[2]] if family=='register' else (
        [[],[0],[2],[0,0],[0,1],[0,2],[2,0],[0,1,0],[0,0,1]] if family=='history' else
        [[],[0],[1],[2],[0,1],[1,0],[0,0],[1,1],[0,2]])
    observer={'projection':'primary','mod':2 if family=='permutation' else None}
    initial=tuple(p['initial']) if isinstance(p['initial'],list) else p['initial']
    current=3 if family=='register' else native_observe(State(initial,()),observer,p)
    suffixes=[[i] for i in range(len(actions))]+[[1,1],[1,2],[2,2]] if family=='register' else [list(x) for length in (1,2) for x in product(range(len(actions)),repeat=length)]
    project=f'LOCAL_TRANSFER006_{index}';scope=f'finite_primary_{index}';store=ResearchStore(path);refs={}
    def event(name,data):
        with patch('time.time',return_value=1793120400+index):
            row=store.record(project,'hypothesis',name,json.dumps(data,sort_keys=True),'hypothesis')
        refs[name]='event:'+str(row['id']);return refs[name]
    for i,word in enumerate(words):
        event('h'+str(i),{'claim_type':'SOURCE_CLAIM','statement':'Finite source history; no equality or proof claim.',
            'word':[actions[k] for k in word],'scope':scope,'version':1,'representation':'native_primitive_port/v1',
            'unknowns':['The actual remaining history is unknown.']})
    event('independent',{'claim_type':'HYPOTHESIS','statement':'Independent question remains available.',
        'word':[],'scope':'independent','version':1,'representation':'native_primitive_port/v1'})
    costs=[0,2,1,3,2,4,2]
    tests=[{'id':f't{i:02}','ordinal':i,'suffix':[actions[k] for k in suffix],
            'cost':sum(costs[k] for k in suffix)+len(suffix)-1} for i,suffix in enumerate(suffixes)]
    hyps=[{'id':'H'+str(i),'ref':refs['h'+str(i)],'weight':i+1,'question':'current','predictive':True,'depends_on':[]} for i in range(9)]
    hyps += [{'id':'D'+str(i),'ref':refs['h'+str(i)],'weight':1,'question':'current','predictive':False,'depends_on':['H'+str(i)]} for i in range(9)]
    hyps += [{'id':'I','ref':refs['independent'],'weight':1,'question':'independent','predictive':False,'depends_on':[]}]
    spec={'family':family,'parameters':p,'histories':[refs['h'+str(i)] for i in range(9)],'independent_ref':refs['independent'],
        'tests':tests,'hypotheses':hyps,'observer':observer,'current_observation':current,
        'representation':'native_primitive_port/v1','scope':scope,'version':1,'unknowns':['Truth outside registered finite D_q is unknown.'],
        'primitive_sha256':primitive_fingerprint(),'known_failures':[]}
    event('root',{'claim_type':'SOURCE_CLAIM','statement':'Native operation definitions and finite question domain only.',
        'source_spec':spec,'scope':scope,'version':1,'representation':'native_primitive_port/v1'})
    with patch('time.time',return_value=1793120400+index):
        obligation=store.frontier.create(project,'Finite primary continuation experiment.',scope,[int(refs['root'].split(':')[1])],status='OPEN')
    history=read_history(path,project)
    q={'id':'finite-primary-v1','project':project,'root_ref':refs['root'],'scope':scope,'version':1,
       'move':{'active_frontier_id':obligation['id'],'parent_event_ids':[int(r.split(':')[1]) for r in refs.values()],
               'proposed_operation':{'mechanism':'readonly_primary_I_T','intent':'advisory'}}}
    return {'id':f'W{index}','family':family,'held_out':hidden,'index':index,'refs':refs,'history':history,'query':q,'database':str(path)}


def view(world: dict, level='C2',budget=None) -> dict:
    return normalize_context(world['history'],'finite primary histories',[world['query']],level,budget)


def frame(world: dict):
    return load_frame(view(world),world['history'],world['query'])
