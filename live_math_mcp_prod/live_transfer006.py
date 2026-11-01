"""One bounded paired-probe I and one partition T, independent of source algebra.

This preserves005's probe/readout/guard loop, not its mod5 inverse shortcut.
Only registered continuations are extended; no programs or signatures are learnt.
"""
import copy
from fractions import Fraction
import time

from normalizer import canonical,digest
from live_transfer006_source import BindingError,Frame,payload,ref_id
from live_transfer006_primitives import Exhausted

VERSION='006.2'


def result(status: str, **fields) -> dict:
    return {'status':status,'core_version':VERSION,'proof_status':'unverified',
            'execution_allowed':False,'completion_allowed':False,**fields}


def endpoint(port, cache: dict, word: list, observer: dict) -> dict:
    """Reuse exact source prefixes, never quotient histories by observations."""
    for length in range(1,len(word)+1):
        prefix=tuple(word[:length])
        if prefix in cache:continue
        previous=cache[prefix[:-1]];state=previous['state'];flags=previous['admissibility'][:]
        if state is not None:
            allowed=port.admissible(state,prefix[-1]);flags.append(allowed)
            state=port.extend(state,prefix[-1]) if allowed else None
        cache[prefix]={'state':state,'admissibility':flags}
    item=cache[tuple(word)]
    if 'readout' not in item:
        item['readout']={'defined':item['state'] is not None,
            'observation':port.observe(item['state'],observer) if item['state'] is not None else None,
            'admissibility':item['admissibility']}
    return item['readout']


def initial_cache(port, word: list) -> dict:
    return {():{'state':port.load(word),'admissibility':[]}}


def metadata(frame: Frame, refs: list[str], port, start: float) -> dict:
    adverse=['event:'+str(i) for i,r in frame.events.items() if r['kind'] in {'failure','failed_check','counterexample','rca'} or r['status'] in {'refuted','counterexample'}]
    sources=frame.sources([frame.query['root_ref']]+refs+adverse)
    return {'source_event_ids':[ref_id(r['ref']) for r in sources],'source_hashes':sources,
        'active_scope':frame.query['scope'],'version':frame.query['version'],'observer':frame.spec['observer'],
        'operations_trace':port.trace,'primitive_calls':port.counts,'seconds':time.perf_counter()-start,
        'known_failures':frame.spec['known_failures']+frame.sources(adverse),'unknowns':frame.spec['unknowns'],
        'independent_verification':'NOT_PERFORMED_BY_GENERATOR; separate oracle receipt required'}


def interpret(frame: Frame, left: str, right: str, max_length: int = 2, max_calls: int = 2048,
              known: tuple = (), observer: dict | None = None, title: str = '') -> dict:
    port=frame.port(max_calls);start=time.perf_counter()
    refs=[r for r in (left,right) if r in frame.spec['histories']]
    try:
        frame.assert_bound()
        if len(refs)!=2:raise BindingError('FOREIGN_OR_UNDECLARED_HISTORY')
        if observer is not None and observer!=frame.spec['observer']:raise BindingError('OBSERVER_ALIGNMENT_REQUIRED')
        if type(max_length) is not int or max_length<0 or max_length>2:raise BindingError('WITNESS_BOUND')
        lc=initial_cache(port,frame.words[left]);rc=initial_cache(port,frame.words[right])
        current=[port.observe(lc[()]['state'],frame.spec['observer']),port.observe(rc[()]['state'],frame.spec['observer'])]
        basis={'current_observations':current,'same_current_observation':current[0]==current[1],
               'prior_distinctions':list(known),'display_title_used':False,'source_identity_implies_equivalence':False}
        if current[0]!=current[1]:
            return result('NO_NEW_DISTINCTION',reason='ALREADY_OBSERVED',novelty_basis=basis,**metadata(frame,refs,port,start))
        # These native sources resolve operation meaning by declared ordinal.
        # Canonicalizing display labels neither merges sources nor grants substitution.
        alphabet=frame.spec['parameters']['actions']
        ordinal_word=lambda word:[alphabet.index(action) for action in word]
        parameters=copy.deepcopy(frame.spec['parameters']);parameters['actions']=list(range(len(alphabet)))
        fingerprint=digest({'project':frame.query['project'],'scope':frame.query['scope'],'version':frame.query['version'],
            'primitive_definition':frame.spec['primitive_sha256'],'observer':frame.spec['observer'],'parameters':parameters,
            'words':sorted([ordinal_word(frame.words[left]),ordinal_word(frame.words[right])]),
            'domain':[ordinal_word(t['suffix']) for t in frame.spec['tests']]})
        if fingerprint in known:
            return result('NO_NEW_DISTINCTION',reason='SEEN_STRUCTURAL_DISTINCTION',fingerprint=fingerprint,novelty_basis=basis,**metadata(frame,refs,port,start))
        tested=0
        for test in sorted(frame.spec['tests'],key=lambda t:(len(t['suffix']),t['ordinal'])):
            if len(test['suffix'])>max_length:continue
            a=endpoint(port,lc,test['suffix'],frame.spec['observer']);b=endpoint(port,rc,test['suffix'],frame.spec['observer']);tested+=1
            if a!=b:
                return result('NEW_DISTINCTION',fingerprint=fingerprint,novelty_basis=basis,
                    witness={'test_id':test['id'],'suffix':test['suffix']},predictions=[a,b],
                    admissibility_trace=[a['admissibility'],b['admissibility']],
                    guard={'histories':[left,right],'current_observation':current[0],'scope':frame.query['scope'],
                           'version':frame.query['version'],'family_bound':True,'substitution_allowed':False},
                    tested_tests=tested,**metadata(frame,refs,port,start))
        return result('UNKNOWN_BOUNDED',reason='NO_WITNESS_IN_EXECUTED_REGISTERED_DOMAIN',novelty_basis=basis,
            tested_tests=tested,exhaustive_registered_domain=tested==len(frame.spec['tests']),
            witness_bound=max_length,asserts_equivalence=False,**metadata(frame,refs,port,start))
    except Exhausted as error:
        return result('UNKNOWN_BOUNDED',reason=str(error),asserts_equivalence=False,**metadata(frame,refs,port,start))
    except (BindingError,ValueError,KeyError,TypeError) as error:
        return result('FAIL_CLOSED',reason=str(error),**metadata(frame,refs,port,start))


def hypotheses(frame: Frame, port, caches: dict, feedback_ref: str | None) -> list:
    rows=copy.deepcopy(frame.spec['hypotheses'])
    for h in rows:
        h['status']='ACTIVE'
        if h['question']=='current' and port.observe(caches[h['ref']][()]['state'],frame.spec['observer'])!=frame.spec['current_observation']:
            h['status']='OUTSIDE_CURRENT_OBSERVATION'
    if feedback_ref is None:return rows
    event=frame.events.get(ref_id(feedback_ref))
    if event is None or event['kind']!='counterexample':raise BindingError('MISSING_COUNTEREXAMPLE_SOURCE')
    receipt=payload(event)['observation']
    if (receipt['scope'],receipt['version'],receipt['observer'])!=(frame.query['scope'],frame.query['version'],frame.spec['observer']):raise BindingError('FEEDBACK_SCOPE_VERSION_OBSERVER')
    test=next(t for t in frame.spec['tests'] if t['id']==receipt['test_id'])
    for h in rows:
        if h['question']=='current' and h['predictive'] and h['status']=='ACTIVE':
            predicted=endpoint(port,caches[h['ref']],test['suffix'],frame.spec['observer'])
            if predicted!=receipt['readout']:h.update(status='EXCLUDED_BY_OBSERVATION',evidence_ref=feedback_ref)
    changed=True
    while changed:
        changed=False;bad={h['id'] for h in rows if h['status']!='ACTIVE'}
        for h in rows:
            if h['status']=='ACTIVE' and set(h['depends_on'])&bad:
                h.update(status='EXCLUDED_DEPENDENCY',evidence_ref=feedback_ref);changed=True
    return rows


def attend(frame: Frame, feedback_ref: str | None = None, max_calls: int = 2048) -> dict:
    port=frame.port(max_calls);start=time.perf_counter();refs=frame.spec['histories']
    try:
        frame.assert_bound()
        caches={ref:initial_cache(port,frame.words[ref]) for ref in refs+[frame.spec['independent_ref']]}
        active_hypotheses=hypotheses(frame,port,caches,feedback_ref)
        active=[h for h in active_hypotheses if h['status']=='ACTIVE' and h['question']=='current' and h['predictive']]
        if len(active)<2:return result('NO_INFORMATIVE_TEST',hypotheses=active_hypotheses,**metadata(frame,refs,port,start))
        total=sum(Fraction(h['weight']) for h in active);ranks=[];rejected=[]
        for test in frame.spec['tests']:
            groups={};counterfactuals=[];safe=True
            for h in active:
                value=endpoint(port,caches[h['ref']],test['suffix'],frame.spec['observer'])
                safe=safe and value['defined'] and all(value['admissibility'])
                counterfactuals.append({'hypothesis':h['id'],'source_ref':h['ref'],'readout':value})
                key=canonical(value);count,weight=groups.get(key,(0,Fraction(0)));groups[key]=(count+1,weight+h['weight'])
            if not safe or len(groups)<2:
                rejected.append({'test_id':test['id'],'reason':'NOT_ROBUSTLY_ADMISSIBLE' if not safe else 'UNINFORMATIVE'});continue
            remaining=sum(count*weight for count,weight in groups.values())/total
            loss=Fraction(test['cost'])+Fraction(7,3)*remaining
            ranks.append({'test_id':test['id'],'suffix':test['suffix'],'cost':test['cost'],'ordinal':test['ordinal'],
                          'expected_remaining':str(remaining),'loss':str(loss),'counterfactuals':counterfactuals})
        ranks.sort(key=lambda r:(Fraction(r['loss']),r['cost'],r['ordinal']))
        if not ranks:return result('NO_INFORMATIVE_TEST',hypotheses=active_hypotheses,rejected=rejected,**metadata(frame,refs,port,start))
        return result('ATTENTION_PROPOSED',test_id=ranks[0]['test_id'],suffix=ranks[0]['suffix'],
            ties=[r['test_id'] for r in ranks if r['loss']==ranks[0]['loss']],ranking=ranks,rejected=rejected,
            hypotheses=active_hypotheses,decision_origin='DETERMINISTIC_T_NOT_LLM',**metadata(frame,refs,port,start))
    except Exhausted as error:return result('UNKNOWN_BOUNDED',reason=str(error),**metadata(frame,refs,port,start))
    except (BindingError,KeyError,ValueError,TypeError,StopIteration) as error:return result('FAIL_CLOSED',reason=str(error),**metadata(frame,refs,port,start))
