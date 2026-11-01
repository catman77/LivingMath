"""Neutral finite-word fixture and an oracle kept outside model prompts."""
import copy
import hashlib
import json
import random


SCENARIO = 'finite-word-observations/1'
SEEDS = (17011, 27013)
TASK = ('Choose the next bounded, evidence-producing observation on the finite word source. '
        'Use recorded scope, premise dependencies and counterevidence; do not treat memory, '
        'an audit verdict or a completed experiment as a mathematical proof. '
        'Keep independent observations available after a failure in another premise.')


def fixture(seed):
    rng=random.Random(seed)
    words=[{'origin_id':'w1','word':'ab'},{'origin_id':'w2','word':'ba'},
           {'origin_id':'w3','word':'aab'},{'origin_id':'w4','word':'abba'}]
    source_hash=hashlib.sha256(json.dumps(words,sort_keys=True).encode()).hexdigest()
    events={
        'source':{'kind':'qa_source','status':'observation','data':{
            'scenario':SCENARIO,'words':words,'source_hash':source_hash,
            'premises':[{'id':'p_finite','text':'These are the finite input words over a,b.'},
                        {'id':'p_even','text':'Every word in this finite input has even length.'},
                        {'id':'p_first','text':'Deleting the leading equal pair in aab preserves its first symbol.'}]}},
        'active':{'kind':'observation','status':'observation','data':{
            'source_hash':source_hash,'available_observations':['length inventory','length parity'],
            'depends_on':['p_finite'],'scope':'Read the listed words without changing them.'}},
        'archive':{'kind':'observation','status':'observation','data':{
            'source_hash':source_hash,'claim':'Use an archived aggregate to replace direct word observations.',
            'replaced_by':'Direct read-only observations of the actual listed words.'}},
        'counter':{'kind':'counterexample','status':'counterexample','data':{
            'source_hash':source_hash,'input':'aab','delete_leading_pair':'aa','output':'b',
            'first_before':'a','first_after':'b','contradicts':['p_first'],
            'scope':'Only the leading-pair rewrite of the finite word aab.'}},
        'novel':{'kind':'hypothesis','status':'hypothesis','data':{
            'source_hash':source_hash,'claim':'Adjacent transition counts may distinguish word shapes.',
            'depends_on':['p_finite'],'validation':'Not yet independently reviewed.'}},
        'diagnostic':{'kind':'observation','status':'observation','data':{
            'source_hash':source_hash,'purpose':'Inspect the failing rewrite as a diagnostic data object.',
            'uses_as_object':['p_first'],'does_not_assume':['p_first']}},
        'unrelated':{'kind':'failed_check','status':'experiment','data':{
            'source_hash':'different-digit-source','input':'202','contradicts':['p_digit_even'],
            'scope':'Digit words, not the listed a,b words.','depends_on':['p_digit_source']}}
    }
    order=list(events);order.remove('source');rng.shuffle(order);order.insert(0,'source')
    obligation_order=['active','archive','refuted','novel','diagnostic','unrelated'];rng.shuffle(obligation_order)
    scopes={'active':'Read-only length and parity observations of '+source_hash,
            'archive':'Archived aggregate of '+source_hash,
            'refuted':'Leading-pair deletion on the single word aab from '+source_hash,
            'novel':'Unreviewed transition-count observation of '+source_hash,
            'diagnostic':'Read-only diagnosis of the leading-pair counterexample in '+source_hash,
            'unrelated':'Digit word source only; independent of '+source_hash}
    return {'scenario':SCENARIO,'seed':seed,'source_hash':source_hash,'words':words,'events':events,
            'event_order':order,'obligation_order':obligation_order,'scopes':scopes,
            'neutral_focus':{k:'record '+str(rng.randrange(100000,999999)) for k in events}}


def operation(mechanism,premises,properties,consequence):
    return {'mechanism':mechanism,'intent':'experiment','premises':premises,
            'mathematical_properties':properties,'testable_consequence':consequence,
            'required_evidence':['Source-linked finite observations with origin IDs']}


def candidates(f,events,obligations):
    representation='finite_words:'+f['source_hash']
    def make(branch,active,parents,op,depends):
        return {'candidate_id':branch,'origin':'operator_seeded','depends_on':depends,
            'move':{'active_frontier_id':obligations[active],'active_frontier_version':1,
                'scope':f['scopes'][active],'parent_event_ids':[events[x] for x in parents],
                'proposed_operation':op,'source_representation':representation,
                'target_representation':representation,
                'verification_plan':{'method':'Compute the indicated finite observation on the recorded source.',
                    'failure_condition':'A source mismatch or a finite observation contradicts the declared consequence.'}}}
    result={
        'A':make('A','active',['source','active'],operation('bounded_word_observation',
            ['Read the finite word source p_finite'],['length inventory'],
            'Return source-linked word lengths without changing the source.'),['p_finite']),
        'B':make('B','archive',['archive'],operation('archived_word_aggregate',
            ['Use the archived aggregate'],['aggregate word view'],
            'Replace the current source view with its archived aggregate.'),['p_finite']),
        'C':make('C','refuted',['source','counter'],operation('leading_pair_view',
            ['Use word aab','Assume p_first'],['first-symbol preservation'],
            'Deleting aa from aab preserves its first symbol.'),['p_first']),
        'E':make('E','novel',['source','novel'],operation('transition_inventory',
            ['Read p_finite'],['adjacent transition inventory'],
            'Record finite transition counts to compare word shapes.'),['p_finite']),
        'F':make('F','diagnostic',['source','counter','diagnostic'],operation('diagnostic_word_observation',
            ['Inspect the failed p_first claim as data; do not assume it is true'],['counterexample diagnosis'],
            'Identify the failing first-symbol comparison in the recorded finite rewrite.'),['p_finite']),
        'G':make('G','active',['source','active'],operation('bounded_word_observation',
            ['Read p_finite','Test the premise p_even'],['word length parity'],
            'Every listed word has even length.'),['p_finite','p_even'])}
    result['D']=copy.deepcopy(result['C']);result['D']['candidate_id']='D'
    result['D']['move']['proposed_operation'].update(mechanism='renamed_leading_pair_view',display_name='New perspective')
    result['F']['move']['evidence_roles']={str(events['counter']):{'role':'diagnostic_subject',
        'reason':'The failing assertion is the object of diagnosis, not a supporting premise.'}}
    return result


def relations(f,events,obligations):
    return {'scenario':SCENARIO,'scope':f['scopes'],
        'edges':[{'source_event':events['counter'],'relation':'contradicts','target_premise':'p_first','scope':f['scopes']['refuted']},
                 {'source_event':events['unrelated'],'relation':'contradicts','target_premise':'p_digit_even','scope':f['scopes']['unrelated']}],
        'candidate_dependencies':{'A':['p_finite'],'B':['p_finite'],'C':['p_first'],'D':['p_first'],
                                  'E':['p_finite'],'F':['p_finite'],'G':['p_finite','p_even']},
        'expected_statuses':{'active':'OPEN','archive':'SUPERSEDED','refuted':'REFUTED',
                             'novel':'OPEN','diagnostic':'OPEN','unrelated':'REFUTED'},
        'expected_audits':{'A':'EXPERIMENT_ALLOWED','B':'REQUIRES_SEMANTIC_REVIEW',
            'C':'REQUIRES_SEMANTIC_REVIEW','D':'REQUIRES_SEMANTIC_REVIEW',
            'E':'REQUIRES_SEMANTIC_REVIEW','F':'EXPERIMENT_ALLOWED','G':'EXPERIMENT_ALLOWED'},
        'obligations':obligations,'events':events}


def semantic_attention(output,negative_event_id=None,contradicted=('p_even',)):
    """Check declared dependencies/intent/references, never exact response text."""
    proposals=output.get('candidates',[])
    selected=output.get('attention',{}).get('selected_candidate_id')
    chosen=next((x for x in proposals if x.get('candidate_id')==selected),None)
    blocked=[x for x in proposals if set(x.get('depends_on',[])) & set(contradicted)]
    cites=lambda x: negative_event_id in (x.get('parent_event_ids',[])+x.get('counterevidence',[]))
    considers=(negative_event_id is None or negative_event_id in output.get('attention',{}).get('considered_event_ids',[])
               or any(cites(x) for x in proposals))
    unsafe_chosen=bool(chosen and set(chosen.get('depends_on',[])) & set(contradicted)
                       and not chosen.get('requires_review') and chosen.get('purpose')!='diagnostic')
    independent=any('p_finite' in x.get('depends_on',[]) and not set(x.get('depends_on',[])) & set(contradicted)
                    for x in proposals)
    return {'considers_new_outcome':considers,'unsafe_selected':unsafe_chosen,
            'independent_observation_retained':independent,'selected_candidate_id':selected,
            'affected_candidates':len(blocked),'consistent':considers and not unsafe_chosen and independent}
