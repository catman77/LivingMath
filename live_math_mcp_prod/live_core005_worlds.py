"""Operator-seeded finite native sources, never ready witness/attention answers."""
import copy
import json
from pathlib import Path
from unittest.mock import patch

from live_core005 import REPRESENTATION, kernel_fingerprint
from normalizer import digest, normalize_context, read_history
from research_store import ResearchStore

SEED = 105005
WORDS = {'h0':[2,2], 'h1':[1,2,2], 'h2':[2,2,2], 'h3':[1,1], 'h4':[3], 'copy4':[0,3]}
SUFFIXES = [[0],[1],[2],[3],[4],[1,1],[1,2],[2,2]]
COSTS = [[0,1,3,2,4,3,4,5], [0,3,1,2,4,2,3,3],
         [0,1,2,3,4,3,2,5], [0,2,3,1,4,3,2,4]]


def create_world(path: Path, index: int, *, weights: list[int] | None = None,
                 costs: list[int] | None = None) -> dict:
    project='LOCAL_CORE005_W'+str(index);scope='finite_register_question_'+str(index)
    store=ResearchStore(path);refs={}
    def record(key,payload,kind='hypothesis',status='hypothesis'):
        with patch('time.time',return_value=1793116800+index):
            row=store.record(project,kind,key,json.dumps(payload,sort_keys=True),status)
        refs[key]='event:'+str(row['id']);return refs[key]
    for name,word in WORDS.items():
        record(name,{'claim_type':'SOURCE_CLAIM','statement':{'word':word},'word':word,
            'scope':scope,'version':1,'representation':REPRESENTATION,
            'unknowns':['The actual hidden history has not been measured.'],
            'method_model':{'input':'native word','operation':'x<-x+k*y,y<-y+k modulo5','output':'register state, then declared observer'}})
    record('independent',{'claim_type':'HYPOTHESIS','statement':'An independent source/question remains available.',
        'word':[1],'scope':'independent_question','version':1,'representation':REPRESENTATION})
    record('point',{'claim_type':'SOURCE_CLAIM','statement':{'polynomial':[0,1],'at0':0},
        'scope':'polynomial_control','version':1,'representation':'point_value'})
    record('germ',{'claim_type':'SOURCE_CLAIM','statement':{'polynomial':[0,1],'identically_zero_germ':False},
        'scope':'polynomial_control','version':1,'representation':'analytic_germ','unknowns':['No equality witness from point evaluation.']})
    record('alias',{'claim_type':'HYPOTHESIS','statement':'Two spellings may denote one register; this supplies no equivalence witness.',
        'scope':scope,'version':1,'representation':REPRESENTATION,'relations':[{'type':'alias_candidate','target_ref':refs['h4']}],
        'equivalence_witness':None})
    observer=['x','parity','x','constant'][index % 4]
    tests=[{'id':'t'+digest([i,suffix])[:8],'suffix':suffix,'cost':(costs or COSTS[index % 4])[i]}
           for i,suffix in enumerate(SUFFIXES)]
    priors=weights or [1,2,3,5,8]
    hypotheses=[{'id':'H'+str(i),'history_ref':refs['h'+str(i)],'weight':priors[i],
                 'question':'current','predictive':True,'depends_on':[]} for i in range(5)]
    hypotheses += [{'id':'D'+str(i),'history_ref':refs['h'+str(i)],'weight':1,
                    'question':'current','predictive':False,'depends_on':['H'+str(i)]} for i in range(5)]
    hypotheses += [{'id':'I','history_ref':refs['independent'],'weight':1,'question':'independent',
                    'predictive':True,'depends_on':[]}]
    spec={'representation':REPRESENTATION,'kernel_sha256':kernel_fingerprint(),'scope':scope,'version':1,
        'native_rule':'start(0,1); append k: (x,y)=((x+k*y)%5,(y+k)%5)',
        'observer':observer,'forbidden_y':0 if index % 4 == 3 else None,
        'histories':[refs[n] for n in WORDS],'independent_ref':refs['independent'],
        'tests':tests,'hypotheses':hypotheses,'uncertainty_price':'7/3',
        'unknowns':['Actual history and next readout unknown; prior weights are declarations, not truths.',
                    'Validity outside this finite native source family is unknown.'],
        'local_rule':{'observed_x':3,'next_x_after_1':1,'omitted_guard':'y=3','origin':'operator_seeded fallible rule'}}
    record('root',{'claim_type':'SOURCE_CLAIM','statement':'Finite native arithmetic source for I/T; no grant or mathematical verification.',
        'scope':scope,'version':1,'representation':REPRESENTATION,'source_spec':spec,
        'method_model':{'input':'source words','operation':'finite native dynamics','output':'unverified distinction/attention proposal'}})
    with patch('time.time',return_value=1793116800+index):
        obligation=store.frontier.create(project,'Distinguish finite source continuations.',scope,
                                        [int(refs['root'].split(':')[1])],status='OPEN')
    history=read_history(path,project)
    query={'id':'finite-core-context-v1','project':project,'root_ref':refs['root'],'scope':scope,'version':1,
        'move':{'active_frontier_id':obligation['id'],'parent_event_ids':[int(r.split(':')[1]) for r in refs.values()],
                'proposed_operation':{'mechanism':'isolated_I_T_preview','intent':'advisory'}}}
    return {'id':'W'+str(index+1),'index':index,'project':project,'scope':scope,'refs':refs,'query':query,
            'history':history,'database':str(path),'environment_commitment':{'actual_word':WORDS['h0'],
             'origin':'operator_precommitted_environment; never passed to I/T or model'}}


def build_view(world: dict, level: str = 'C2', budget=None) -> dict:
    return normalize_context(world['history'],'finite native distinction', [world['query']],level,budget)


def environmental_readout(world: dict, suffix: list[int]) -> list:
    """Precommitted environment, separate from generator and oracle."""
    word=world['environment_commitment']['actual_word']+suffix
    x=0;y=1
    for symbol in word:
        previous_y=y;x=(x+symbol*previous_y)%5;y=(previous_y+symbol)%5
    observer=['x','parity','x','constant'][world['index'] % 4]
    value=x if observer=='x' else x%2 if observer=='parity' else 0
    return [value, world['index'] % 4 != 3 or y!=0]


def append_observation(world: dict, attention: dict) -> tuple[dict,str]:
    """Append only to this isolated synthetic DB, retaining the original source."""
    store=ResearchStore(Path(world['database']))
    readout=environmental_readout(world,attention['suffix'])
    with patch('time.time',return_value=1793116900+world['index']):
        event=store.record(world['project'],'counterexample','Bounded environmental readout',json.dumps({
            'claim_type':'COUNTEREXAMPLE','scope':world['scope'],'version':1,'representation':REPRESENTATION,
            'observation':{'test_id':attention['test_id'],'readout':readout,'scope':world['scope'],
                'version':1,'observer':['x','parity','x','constant'][world['index'] % 4],
                'origin':'operator_precommitted_environment'},
            'statement':'A concrete readout excludes conflicting bound predictions; this is not a proof.'},sort_keys=True),
            'experiment',parent_id=int(world['refs']['root'].split(':')[1]))
    after=copy.deepcopy(world);after['history']=read_history(Path(world['database']),world['project'])
    after['query']['move']['parent_event_ids'].append(event['id'])
    return after,'event:'+str(event['id'])
