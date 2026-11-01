"""Fixed source-only007 fixtures; certificates contain no target pair or suffix."""
from itertools import product
import json
from pathlib import Path
from unittest.mock import patch

from normalizer import digest,read_history,normalize_context
from research_store import ResearchStore
from live_constructive007_native import native_fingerprint
from live_constructive007_source import load_frame

SEED=107007


def swap(n,a,b):
    p=list(range(n));p[a],p[b]=p[b],p[a];return p


def create_world(path: Path,index: int):
    families=['affine','permutation','erasure','affine','permutation','erasure','opaque','boundary'];family=families[index]
    held=index in (3,4,5)
    if family=='affine':
        coeff=[0,3,6,9,12,5,1,2] if held else [0,2,4,6,8,10,1]
        initial=[0,1];p={'family':family,'initial':initial,'coefficients':coeff,'modulus':15 if held else 12}
        h0=[7] if held else [6];h1=h0+([5] if held else [3]);words=[h0,h1,h0,[],[0],h0+[0]]
        law='affine-injective';width=2;current=2 if held else 1
    elif family=='permutation':
        n=5 if held else 4;initial=list(range(n));rotate=[0]+list(range(2,n))+[1]
        ps=[initial,swap(n,1,2),swap(n,2,3),rotate,swap(n,0,n-1 if held else 2),swap(n,0,2 if held else 1),swap(n,0,1 if held else 3)]
        p={'family':family,'initial':initial,'permutations':ps};words=[[],[1],[],[5],[1,1],[1,4]]
        law='right-projection';width=n;current=0
    elif family=='erasure':
        initial=list('rrqrrsrt') if held else list('aabaac');cuts=[0,0,1,0,3,2,8] if held else [0,0,0,1,2,3,6]
        p={'family':family,'initial':initial,'cuts':cuts};words=[[],[4] if held else [5],[],[6],[6,6],[0]]
        law='prefix-projection';width=len(initial);current=initial[0]
    else:
        p={'family':family,'initial':[0]};words=[[0],[1],[0],[2],[0,0],[1,0]];law=None;width=1;current=0
    n=len(p.get('coefficients',p.get('permutations',p.get('cuts',[0,1,2,3]))))
    actions=[f'g{SEED+index}_{i}' for i in range(n)];p['actions']=actions
    project=f'LOCAL_CONSTRUCTIVE007_{index}';scope=f'source_law_scope_{index}';store=ResearchStore(path);refs={}
    def record(key,data):
        with patch('time.time',return_value=1793131200+index):row=store.record(project,'hypothesis',key,json.dumps(data,sort_keys=True),'hypothesis')
        refs[key]='event:'+str(row['id']);return row
    for i,word in enumerate(words):record('h'+str(i),{'claim_type':'SOURCE_CLAIM','statement':'Raw finite source history, not an equivalence claim.',
        'word':[actions[x] for x in word],'scope':scope,'version':1,'representation':'native_007/v1'})
    record('independent',{'claim_type':'HYPOTHESIS','statement':'Independent question retained.','word':[],'scope':'independent','version':1,'representation':'native_007/v1'})
    suffixes=[list(x) for length in (1,2) for x in product(range(n),repeat=length)] if family in {'opaque','boundary'} else [[i] for i in range(n)]+[[0,0],[1,0],[0,1]]
    tests=[{'id':f't{i:02}','ordinal':i,'suffix':[actions[x] for x in word],'cost':1+sum((x%3)+1 for x in word)} for i,word in enumerate(suffixes)]
    hyps=[{'id':'H'+str(i),'ref':refs['h'+str(i)],'weight':i+1,'predictive':True,'question':'current','depends_on':[]} for i in range(6)]
    hyps += [{'id':'D'+str(i),'ref':refs['h'+str(i)],'weight':1,'predictive':False,'question':'current','depends_on':['H'+str(i)]} for i in range(6)]
    hyps += [{'id':'I','ref':refs['independent'],'weight':1,'predictive':False,'question':'independent','depends_on':[]}]
    observer={'projection':'primary','mod':None}
    spec={'family':family,'parameters':p,'histories':[refs['h'+str(i)] for i in range(6)],'independent_ref':refs['independent'],
        'tests':tests,'hypotheses':hyps,'observer':observer,'current_observation':current,'scope':scope,'version':1,
        'representation':'native_007/v1','primitive_sha256':native_fingerprint(),'known_failures':[],
        'unknowns':['Actual hidden source history and truth outside registered D are unknown.']}
    root=record('root',{'claim_type':'SOURCE_CLAIM','statement':'Native source definitions, not witness answers.','source_spec':spec,'scope':scope,'version':1,'representation':'native_007/v1'})
    with patch('time.time',return_value=1793131200+index):obligation=store.frontier.create(project,'Test finite source-certified interpretation.',scope,[root['id']],status='OPEN')
    certificate_ref=None
    if law:
        before=read_history(path,project);raw=next(e for e in before['tables']['events'] if e['id']==root['id'])
        cert={'schema':'separating-coordinate/v1','source_ref':refs['root'],'source_hash':digest(raw),'project':project,'scope':scope,'version':1,
            'observer_hash':digest(observer),'native_hash':native_fingerprint(),'kind':law,'coverage':list(range(width)),
            'guard':{'total_admissibility':True,'width':width}}
        record('law',{'claim_type':'FORMAL_CLAIM','statement':'Candidate bound program-schema law; not server verification.','source_certificate':cert,
            'scope':scope,'version':1,'representation':'native_007/v1'})
        certificate_ref=refs['law']
    history=read_history(path,project)
    q={'id':'constructive007-source','project':project,'root_ref':refs['root'],'scope':scope,'version':1,
       'move':{'active_frontier_id':obligation['id'],'parent_event_ids':[int(r.split(':')[1]) for r in refs.values()],
       'proposed_operation':{'mechanism':'readonly_source_law_interpretation','intent':'advisory'}}}
    return {'id':f'W{index}','index':index,'family':family,'held_out':held,'history':history,'query':q,'refs':refs,
            'certificate_ref':certificate_ref,'database':str(path)}


def view(w,level='C2',budget=None):return normalize_context(w['history'],'source-certified interpretation',[w['query']],level,budget)
def frame(w):return load_frame(view(w),w['history'],w['query'])
