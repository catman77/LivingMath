"""Frozen-corpus experiment and honest novelty decision; generation has no evaluator input."""
import argparse
import asyncio
from copy import deepcopy
import datetime
import gzip
import hashlib
import json
from pathlib import Path
import time
from typing import Any

from davcore.adapters import Adapter, AdapterSpec
from davcore.ast import Formula, digest, implication
from davcore.finite import check
from davcore.models import Budget
from .contract import SourceGraph, ProposalRequest
from .generator import semantic_fingerprint, rename_symbols
from .mcp import generate
from .network import Network, fire
from .checker import check_translation, evaluate_laws, repair, pareto


def save(path: Path, value) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(''.join(json.dumps(r,ensure_ascii=False,sort_keys=True,allow_nan=False)+'\n' for r in rows))


def verify_freeze(root: Path) -> dict:
    frozen=json.loads((root/'source-freeze.json').read_text())
    for name,h in frozen['frozen_files'].items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=h:raise ValueError('FROZEN_SOURCE_OR_CRITERIA_DRIFT:'+name)
    if hashlib.sha256((root/'target-signature.json').read_bytes()).hexdigest()!=frozen['target_signature_sha256']:
        raise ValueError('TARGET_SIGNATURE_DRIFT')
    return frozen


def verify_source_spans(root: Path) -> dict:
    public=json.loads((root/'frozen/public-passages.json').read_text())
    lines={line['verse_line']:line for p in public['passages'] for line in p['lines']}
    spans=[json.loads(row) for row in (root/'frozen/source-map.jsonl').read_text().splitlines()]
    failures=[]
    for span in spans:
        line=lines[span['verse_line']];start=span['byte_start']-line['byte_start'];end=span['byte_end']-line['byte_start']
        if line['text'].encode()[start:end]!=span['exact_short_quote'].encode():failures.append(span['span_id'])
        if span['xml_path']!=line['xml_path']:failures.append(span['span_id']+':xml')
    poem=(root/'frozen/pushkin-tucha.txt').read_bytes()
    for span in json.loads((root/'frozen/poem-spans.json').read_text()):
        if poem[span['byte_start']:span['byte_end']]!=span['exact_quote'].encode():failures.append(span['span_id'])
    if failures:raise ValueError('SOURCE_BYTE_OR_XML_ADDRESS_MISMATCH:'+str(failures))
    return {'status':'PASS','Ripley_spans_checked':len(spans),'poem_lines_checked':12,
            'scope':'Exact byte slices against accepted public transcription; not original scan collation or semantic entailment.'}


def frame_vectors(c: dict) -> list:
    """Fixed existing-AST frame-law truth vectors, independent of candidate string names."""
    n=Network.model_validate(c['network']);out=[]
    for r in range(len(n.reactions)):
        for s in range(len(n.species)):
            out.append([((fire(n,r,x)>>s)&1)==((x>>s)&1) for x in range(2**len(n.species))])
    return out


async def control_checks(entry: dict, direct: dict, batch: dict) -> dict:
    g=SourceGraph.model_validate(entry['graph'])
    generator_inputs=[];generator_wall_ms=0.
    async def controlled_generate(request):
        nonlocal generator_wall_ms
        before=time.monotonic();response=await generate(request)
        generator_wall_ms+=(time.monotonic()-before)*1000
        generator_inputs.append({'input':request.model_dump(),'input_sha256':digest(request.model_dump()),
                                 'candidate_count':len(response['candidates'])})
        return response
    alpha=rename_symbols(direct)
    rx_names={r['id']:'alpha_reaction_'+str(i) for i,r in enumerate(alpha['network']['reactions'])}
    for r in alpha['network']['reactions']:r['id']=rx_names[r['id']]
    for r in alpha['reverse_map']:r['reaction_id']=rx_names[r['reaction_id']]
    target_alpha=semantic_fingerprint(direct)==semantic_fingerprint(alpha) and check_translation(g,alpha)['status']=='FORMAL_TRANSLATION_VALID'
    renamed=deepcopy(entry['graph']);ids={n['id']:'alpha_node_'+str(i) for i,n in enumerate(renamed['nodes'])}
    for node in renamed['nodes']:node['id']=ids[node['id']]
    for i,rel in enumerate(renamed['relations']):
        rel['id']='alpha_relation_'+str(i);rel['src']=ids[rel['src']];rel['dst']=ids[rel['dst']]
    ar=await controlled_generate(ProposalRequest(graph=SourceGraph.model_validate(renamed),allowed_edits=['transition']))
    source_alpha=semantic_fingerprint(direct)==semantic_fingerprint(ar['candidates'][0])
    seq=deepcopy(entry['graph']);rel=next((r for r in seq['relations'] if r['kind']=='sequence'),None)
    seq_result: dict[str,Any]={'status':'NOT_APPLICABLE_NO_SEQUENCE_RELATION'}
    if rel:
        before=deepcopy(rel);rel['src'],rel['dst']=rel['dst'],rel['src']
        transformed=(await controlled_generate(ProposalRequest(graph=SourceGraph.model_validate(seq),allowed_edits=['transition'])))['candidates'][0]
        seq_result={'status':'PASS' if frame_vectors(transformed)!=frame_vectors(direct) else 'FAIL',
                    'original_relation':before,'counterfactual_relation':rel,
                    'frame_truth_vectors_changed':frame_vectors(transformed)!=frame_vectors(direct),
                    'source_file_modified':False,'interpretation':'Controlled change of narrative relation, not asserted physical time.'}
    bad=next(c for c in batch['candidates'] if c['edit']=='merge_roles')
    conflict=check_translation(g,bad)['conflicts'][0]
    deleted=deepcopy(entry['graph']);deleted['relations']=[r for r in deleted['relations'] if r['id']!=conflict['relation_id']]
    counterfactual=deepcopy(bad);counterfactual['source_graph_sha256']=digest(deleted)
    counterfactual['loss_ledger']=[r for r in bad['loss_ledger'] if r['source_relation_id']!=conflict['relation_id']
                                 or r['kind']=='ROLE_COLLAPSE']
    after=check_translation(SourceGraph.model_validate(deleted),counterfactual)
    # Role deletion is tested independently by reversing a source actor/role relation.
    roles=deepcopy(entry['graph']);role=next((r for r in roles['relations'] if r['kind']=='role'),None)
    role_result: dict[str,Any]={'status':'NOT_APPLICABLE_NO_ROLE_RELATION'}
    if role:
        roles['relations']=[r for r in roles['relations'] if r['id']!=role['id']]
        changed=(await controlled_generate(ProposalRequest(graph=SourceGraph.model_validate(roles),allowed_edits=['transition'])))['candidates'][0]
        role_result={'status':'PASS' if semantic_fingerprint(changed)!=semantic_fingerprint(direct) else 'FAIL',
                     'removed_relation':role,'original_reaction_count':len(direct['network']['reactions']),
                     'new_reaction_count':len(changed['network']['reactions'])}
    return {'source':entry['name'],'alpha_target':'PASS' if target_alpha else 'FAIL',
        'alpha_source_identifiers':'PASS' if source_alpha else 'FAIL','sequence':seq_result,
        'contrast_deletion':{'status':'PASS' if after['status']=='FORMAL_TRANSLATION_VALID' else 'FAIL',
            'original_conflict':conflict,'guard_after_contrast_deletion':after['status'],
            'scope':'Counterfactual input only, not a repair of the original source.'},'role_deletion':role_result,
        'generator_control_inputs':generator_inputs,'generator_control_wall_ms':generator_wall_ms}


def lexical_baseline(entry: dict, direct: dict, labels: dict, spans: dict) -> dict:
    """Naive first-token equivalence, symbolic only; no chemistry lexicon or target answers."""
    out=deepcopy(direct);g=entry['graph'];bins: dict[str,str]={};replacement: dict[str,str]={}
    for node in g['nodes']:
        ref=node['source_refs'][0];text=spans[ref].get('exact_short_quote',spans[ref].get('exact_quote',''))
        first=(text.casefold().split() or ['empty'])[0].strip(',.;:!')
        old=out['mapping'][node['id']]
        target=bins.setdefault(first,old);replacement[old]=target;out['mapping'][node['id']]=target
    for reaction in out['network']['reactions']:
        for side in ['reactants','products']:reaction[side]={replacement.get(k,k):1 for k in reaction[side]}
    for s in out['network']['species']:
        refs={ref for node in g['nodes'] if out['mapping'][node['id']]==s['id'] for ref in node['source_refs']}
        if refs:s['source_refs']=sorted(refs)
    for target in sorted(set(out['mapping'].values())):
        origins=[node for node,value in out['mapping'].items() if value==target]
        if len(origins)>1:
            out['loss_ledger'].append({'kind':'MANY_TO_ONE_COLLAPSE','source_nodes':origins,'target_species':target,
                'source_relation_id':'lexical_equivalence_not_attested','reason':'First-token binning erases independent source roles.',
                'status':'UNRESOLVED'})
    out['edit']='lexical_first_token';out['parent_candidate_id']=out.pop('candidate_id')
    out['observed_semantics_sha256']=semantic_fingerprint(out);out['candidate_id']=digest(out)
    return out


async def run(root: Path, out: Path) -> dict:
    start=time.monotonic();freeze=verify_freeze(root);out.mkdir(parents=True,exist_ok=True)
    save(out/'source-provenance-check.json',verify_source_spans(root))
    entries=json.loads((root/'frozen/graphs.json').read_text());labels=json.loads((root/'frozen/source-labels.json').read_text())
    train=[x for x in entries if x['split']=='train'];remaining=[x for x in entries if x['split']!='train']
    candidates=[];models=[];laws=[];repairs=[];losses=[];controls=[];baselines=[];input_records=[];batches={}
    cost={'generator_wall_ms':0.,'DAV_operation_applications':0,'DAV_checks':0,'generator_candidates':0,
          'generator_invocations':0,'budget_per_branch':json.loads((root/'frozen/criteria.json').read_text())['budget_per_branch']}
    trace=gzip.open(out/'checker-logs.jsonl.gz','wt',encoding='utf-8')
    def sink(row):
        trace.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+'\n')
        cost['DAV_checks']+=1;cost['DAV_operation_applications']+=row['result']['metrics']['operation_applications']
    spans={x['span_id']:x for x in [json.loads(l) for l in (root/'frozen/source-map.jsonl').read_text().splitlines()]}
    spans.update({x['span_id']:x for x in json.loads((root/'frozen/poem-spans.json').read_text())})
    async def investigate(entry,phase):
        g=SourceGraph.model_validate(entry['graph']);request=ProposalRequest(graph=g)
        input_records.append({'phase':phase,'input':request.model_dump(),'input_sha256':digest(request.model_dump()),
            'contains_text_or_labels':False,'contains_expected_mapping_or_checker':False})
        tick=time.monotonic();batch=await generate(request);cost['generator_wall_ms']+=(time.monotonic()-tick)*1000
        cost['generator_invocations']+=1;cost['generator_candidates']+=len(batch['candidates']);batches[g.id]=batch
        for c in batch['candidates']:
            checked=check_translation(g,c);c['source_name']=entry['name'];c['phase']=phase
            candidates.append(c);losses.extend({'candidate_id':c['candidate_id'],**loss} for loss in c['loss_ledger'])
            # A formally consistent wrong translation can have true laws: measure this ablation too.
            model_laws=evaluate_laws(c,sink=sink)
            for law in model_laws:
                law['source_fidelity']=checked['status']
                law['source_binding_admissible']=checked['status']=='FORMAL_TRANSLATION_VALID'
            laws.extend(model_laws);models.append({'candidate_id':c['candidate_id'],'source_name':entry['name'],
                'network':c['network'],'mapping':c['mapping'],'assumptions':c['assumptions'],'check':checked,
                'nontrivial_proved':sum(l['nontrivial'] for l in model_laws),
                'observed_semantics_sha256':c['observed_semantics_sha256'],'edit':c['edit']})
        bad=next(c for c in batch['candidates'] if c['edit']=='merge_roles')
        rr=repair(g,bad);rr['recheck']=check_translation(g,rr['candidate']);rr['source_name']=entry['name'];repairs.append(rr)
        direct=next(c for c in batch['candidates'] if c['edit']=='transition')
        controls.append(await control_checks(entry,direct,batch))
        control=controls[-1]
        cost['generator_invocations']+=len(control['generator_control_inputs'])
        cost['generator_wall_ms']+=control['generator_control_wall_ms']
        cost['generator_candidates']+=sum(x['candidate_count'] for x in control['generator_control_inputs'])
        input_records.extend({'phase':'CONTROL_'+phase,**x,'contains_text_or_labels':False,
                              'contains_expected_mapping_or_checker':False} for x in control['generator_control_inputs'])
        lexical=lexical_baseline(entry,direct,labels,spans);lexcheck=check_translation(g,lexical)
        lexical_laws=evaluate_laws(lexical,sink=sink)
        for law in lexical_laws:
            law['source_fidelity']=lexcheck['status'];law['source_binding_admissible']=lexcheck['status']=='FORMAL_TRANSLATION_VALID'
        laws.extend(lexical_laws)
        losses.extend({'candidate_id':lexical['candidate_id'],**loss} for loss in lexical['loss_ledger'])
        models.append({'candidate_id':lexical['candidate_id'],'source_name':entry['name'],'network':lexical['network'],
            'mapping':lexical['mapping'],'assumptions':lexical['assumptions'],'check':lexcheck,
            'nontrivial_proved':sum(l['nontrivial'] for l in lexical_laws),
            'observed_semantics_sha256':lexical['observed_semantics_sha256'],'edit':lexical['edit']})
        candidates.append(lexical)
        choices={'A':direct,'B':lexical,
                 'C':min((c for c in batch['candidates'] if check_translation(g,c)['status']=='FORMAL_TRANSLATION_VALID'),
                         key=lambda c:len(set(c['mapping'].values()))+len(c['network']['reactions'])),
                 'D':min(batch['candidates'],key=lambda c:len(set(c['mapping'].values()))+len(c['network']['reactions']))}
        rows=[]
        for branch,c in choices.items():
            verdict=check_translation(g,c)
            nl=sum(l['nontrivial'] for l in laws if l['candidate_id']==c['candidate_id'])
            rows.append({'branch':branch,'candidate_id':c['candidate_id'],'check':verdict['status'],
                'selection_guard_enabled':branch!='D','shared_budget_upper_bound':cost['budget_per_branch'],
                'actual_distinct_proposals':1 if branch in ['A','B'] else len(batch['candidates']),
                'metrics':{'source_fidelity':len(set(c['mapping'].values()))/len(g.nodes) if not verdict['conflicts'] else 0.,'nontriviality':nl,
                    'heldout_predictive_relation':0,'transfer_stability':int(controls[-1]['alpha_target']=='PASS'),
                    'model_complexity':len(set(c['mapping'].values()))+len(c['network']['reactions']),
                    'epistemic_integrity':1}})
        baselines.append({'source_name':entry['name'],'branches':rows,'pareto':pareto(rows),
            'copy_only':{'new_structural_laws':0,'status':'SOURCE_REPLAY_ONLY'},
            'direct_template':{'candidate_id':direct['candidate_id'],'new_structural_laws':0},
            'LLM':{'status':'NOT_RUN','reason':'No external model/API baseline executed.'},
            'budget_caveat':'Same ceilings, actual proposal spend differs by strategy; no superiority claim from raw law counts.'})
    try:
        for entry in train:await investigate(entry,'TRAIN_BEFORE_HOLDOUT')
        # Compose source-addressed subviews without a cross-Gate temporal edge or identity.
        subviews=[]
        for entry in train:
            source=entry['graph'];chosen=set()
            contrast=next(r for r in source['relations'] if r['kind']=='contrast')
            chosen.update([contrast['src'],contrast['dst']])
            for r in source['relations']:
                if r['kind'] in {'contrast','order','repeat'}:continue
                enlarged=chosen|{r['src'],r['dst']}
                if len(enlarged)<=4:chosen=enlarged
            subviews.append({'nodes':[n for n in source['nodes'] if n['id'] in chosen],
                'relations':[r for r in source['relations'] if {r['src'],r['dst']}<=chosen],
                'omitted_source_nodes':[n['id'] for n in source['nodes'] if n['id'] not in chosen]})
        joined=SourceGraph.model_validate({'id':'composed_'+digest([e['graph']['id'] for e in train])[:16],
            'nodes':[n for view in subviews for n in view['nodes']],
            'relations':[r for view in subviews for r in view['relations']]})
        request=ProposalRequest(graph=joined,allowed_edits=['transition','catalytic']);tick=time.monotonic()
        composed=await generate(request);cost['generator_wall_ms']+=(time.monotonic()-tick)*1000
        cost['generator_invocations']+=1;cost['generator_candidates']+=len(composed['candidates'])
        input_records.append({'phase':'TRAIN_COMPOSITION_BEFORE_HOLDOUT','input':request.model_dump(),
            'input_sha256':digest(request.model_dump()),'contains_text_or_labels':False,'contains_expected_mapping_or_checker':False})
        c=composed['candidates'][0];network=Network.model_validate(c['network'])
        first_component={r['id'] for r in subviews[0]['relations']}
        i=next(k for k,r in enumerate(network.reactions) if set(r.source_relation_ids)<=first_component)
        j=next(k for k,r in enumerate(network.reactions) if not set(r.source_relation_ids)&first_component)
        from davcore.ast import Apply, Eq, term
        composition_formula=Formula(body=Eq(left=Apply(operation='R'+str(j),argument=term('R'+str(i))),
            right=Apply(operation='R'+str(i),argument=term('R'+str(j)))))
        composition_evidence=check(Adapter(AdapterSpec(kind='reaction_network',reaction_network=network)),
            composition_formula,budget=Budget(max_states=256))
        sink({'candidate_id':c['candidate_id'],'result':composition_evidence})
        save(out/'cross-gate-composition.json',{'status':'PASS' if composition_evidence['status']=='proved' else 'FAIL',
            'source_subviews':subviews,'candidate':c,'check':check_translation(joined,c),
            'evidence':composition_evidence,'physical_kinetic_order_assumed':False,'cross_gate_equalities_added':False,
            'scope':'Disjoint composition of two explicit source subviews, not a model of all omitted text.',
            'new_structural_source_law':False,'complete_five_gate_union':{'status':'NOT_CONSTRUCTIBLE_WITH_CURRENT_BOUND',
                'required_source_roles':sum(len(e['graph']['nodes']) for e in entries if 'gate' in e),
                'max_species':8,'reason':'Full disjoint union exceeds the frozen finite bound; no unsupported role merge is introduced.'}})
        # A conditional commutation hypothesis learned from the first two reaction commands.
        # Commit source-independent AST and receipts BEFORE any holdout graph reaches the worker.
        trained=[]
        for entry in train:
            c=next(c for c in candidates if c['source_graph_id']==entry['graph']['id'] and c['edit']=='transition')
            n=Network.model_validate(c['network']);first=next(iter(n.reactions[0].reactants));idx=next(i for i,s in enumerate(n.species) if s.id==first)
            from davcore.ast import Apply, Eq, Implies, term
            hypothesis=Formula(body=Implies(premise=Eq(left=term('S'+str(idx)),right=term('Zero')),
                conclusion=Eq(left=Apply(operation='R1',argument=term('R0')),right=Apply(operation='R0',argument=term('R1')))))
            actual=check(Adapter(AdapterSpec(kind='reaction_network',reaction_network=n)),hypothesis)
            trained.append({'source':entry['name'],'candidate_id':c['candidate_id'],'formula':hypothesis.canonical_ast(),
                'status':actual['status'],'support':actual['support'],'conclusion_failures':actual['nontrivial_conclusion_failures']})
        prediction={'relation':'absence_of_first_source_role_implies_commutation_of_first_two_source_operations',
            'training_evidence':trained,'source_claim_status':'HYPOTHESIS_NOT_A_TEXTUAL_ATTESTATION',
            'expected_source_answer_supplied':False,'definition_bound_risk':True,
            'success_requires':'New independent addressed source relation, nontrivial on holdout, beyond copy/template.'}
        save(out/'prediction-before-holdout.json',prediction)
        jsonl(out/'training-candidate-commit.jsonl',[c for c in candidates if c.get('phase')=='TRAIN_BEFORE_HOLDOUT'])
        commit={'source_freeze_sha256':hashlib.sha256((root/'source-freeze.json').read_bytes()).hexdigest(),
            'prediction_sha256':hashlib.sha256((out/'prediction-before-holdout.json').read_bytes()).hexdigest(),
            'candidate_commit_sha256':hashlib.sha256((out/'training-candidate-commit.jsonl').read_bytes()).hexdigest(),
            'inputs_before_commit':[x['input_sha256'] for x in input_records],
            'committed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'holdout_graph_ids_not_sent_yet':[e['graph']['id'] for e in remaining if e['split']=='cross_gate_holdout']}
        save(out/'hypothesis-commit.json',commit)
        for entry in remaining:await investigate(entry,'AFTER_PREDICTION_COMMIT_'+entry['split'].upper())
        challenge=[];holdout_repairs=[]
        for entry in remaining:
            if entry['split']!='cross_gate_holdout':continue
            c=next(c for c in candidates if c['source_graph_id']==entry['graph']['id'] and c['edit']=='transition')
            n=Network.model_validate(c['network']);i=next(j for j,s in enumerate(n.species) if s.id==next(iter(n.reactions[0].reactants)))
            from davcore.ast import Apply, Eq, Implies, term
            f=Formula(body=Implies(premise=Eq(left=term('S'+str(i)),right=term('Zero')),
                conclusion=Eq(left=Apply(operation='R1',argument=term('R0')),right=Apply(operation='R0',argument=term('R1')))))
            evidence=check(Adapter(AdapterSpec(kind='reaction_network',reaction_network=n)),f);sink({'candidate_id':c['candidate_id'],'result':evidence})
            challenge.append({'source':entry['name'],'source_spans':sorted({ref for r in entry['graph']['relations'] for ref in r['source_refs']}),
                'formula':f.canonical_ast(),'formal_status':evidence['status'],'nontrivial_conclusion_failures':evidence['nontrivial_conclusion_failures'],
                'counterexample':evidence['counterexample'],'new_source_relation_independently_confirmed':False,
                'novelty_status':'NO_NEW_STRUCTURAL_TRANSFER','reason':'Conditional target law does not establish an unannotated source relation; copy/template tie remains.'})
            holdout_repairs.append({'source':entry['name'],'original_prediction_sha256':commit['prediction_sha256'],
                'failure':'NONTRIVIALITY_LOST_ON_WITHHELD_SOURCE','source_refs':challenge[-1]['source_spans'],
                'witness':{'first_two_reactions':[r.model_dump() for r in n.reactions[:2]],
                    'conclusion_failures':evidence['nontrivial_conclusion_failures'],
                    'formal_status':evidence['status']},
                'local_revision':'Withdraw cross-Gate generalization; retain conditional commutation only for the addressed interacting-command models.',
                'source_modified':False,'checker_modified':False,'G3_still_failed':True,
                'search_status':'SEARCH_EXHAUSTED_IN_FROZEN_EDIT_FAMILY_NOT_A_UNIVERSAL_IMPOSSIBILITY'})
        literary=json.loads((root/'frozen/holdouts.json').read_text())['literary_lines']
        literary_challenge={'withheld_line_ids':[l['span_id'] for l in literary],
            'predicted_relation':'conditional command commutation, not a lexical guess',
            'source_confirmation':'NOT_ESTABLISHED','reason':'Heldout narrative introduces changed modality/actor; frozen training B-relations do not justify identifying it with a command-commutation law.',
            'status':'NO_NEW_STRUCTURAL_TRANSFER','source_file_unchanged':True}
        # A real line-order control, using the same first six public lines and no withheld words.
        clause_nodes=[{'id':'line_node_'+str(i),'kind':'textual_clause','source_refs':['poem-line-'+str(i)]} for i in range(1,7)]
        async def ordered(order):
            packet=SourceGraph.model_validate({'id':'poem_order_control','nodes':clause_nodes,'relations':[
                {'id':'line_sequence_'+str(j),'kind':'sequence','src':'line_node_'+str(a),'dst':'line_node_'+str(b),
                 'source_refs':['poem-line-'+str(a),'poem-line-'+str(b)],'grade':'B'} for j,(a,b) in enumerate(zip(order,order[1:]))]})
            request=ProposalRequest(graph=packet,allowed_edits=['transition']);tick=time.monotonic();answer=await generate(request)
            cost['generator_wall_ms']+=(time.monotonic()-tick)*1000;cost['generator_invocations']+=1;cost['generator_candidates']+=1
            input_records.append({'phase':'LITERARY_LINE_ORDER_CONTROL_AFTER_COMMIT','input':request.model_dump(),
                'input_sha256':digest(request.model_dump()),'contains_text_or_labels':False,'contains_expected_mapping_or_checker':False})
            return answer['candidates'][0]
        order_before=[1,2,3,4,5,6];order_after=[2,1,3,4,5,6]
        ordered_before=await ordered(order_before);ordered_after=await ordered(order_after)
        line_control={'status':'PASS' if frame_vectors(ordered_before)!=frame_vectors(ordered_after) else 'FAIL',
            'source':'Pushkin Tucha','original_line_order':order_before,'counterfactual_line_order':order_after,
            'fixed_DAV_frame_law_truth_vectors_changed':frame_vectors(ordered_before)!=frame_vectors(ordered_after),
            'counterfactual_only':True,'frozen_source_modified':False,'withheld_lines_used':False}
        known=check(Adapter(AdapterSpec(kind='gate6')),implication('P','One','Q','One'))
        gate=next(e for e in entries if e.get('gate')==6);batch=batches[gate['graph']['id']]
        cat=next(c for c in batch['candidates'] if c['edit']=='catalytic');latent=next(c for c in batch['candidates'] if c['edit']=='latent_guard')
        pnode=gate['graph']['nodes'][0]['id'];qnode=gate['graph']['nodes'][3]['id'];conj=next(r for r in gate['graph']['relations'] if r['kind']=='conjunction')
        network_witness=[]
        for c in [cat,latent]:
            n=Network.model_validate(c['network']);positions={s.id:i for i,s in enumerate(n.species)}
            p=positions[c['mapping'][pnode]];q=positions[c['mapping'][qnode]]
            j=next(i for i,r in enumerate(n.reactions) if conj['id'] in r.source_relation_ids)
            before=1<<p;after=fire(n,j,before)
            network_witness.append({'candidate_id':c['candidate_id'],'edit':c['edit'],'initial_full_state':before,
                'final_full_state':after,'visible_P_before':(before>>p)&1,'visible_P_after':(after>>p)&1,
                'hidden_Q_after':(after>>q)&1,'reaction':n.reactions[j].model_dump(),
                'latent_prerequisite_status':'COMPETING_C_ASSUMPTION_UNKNOWN_NOT_SOURCE_FACT'})
        jsonl(out/'translations.jsonl',candidates);jsonl(out/'formal-models.jsonl',models)
        jsonl(out/'laws-and-witnesses.jsonl',laws+[{'kind':'KNOWN_GATE6_NEGATIVE_CONTROL','evidence':known,
            'new_discovery':False,'two_network_realizations':network_witness}])
        jsonl(out/'repairs-and-counterexamples.jsonl',repairs);jsonl(out/'loss-ledger.jsonl',losses)
        jsonl(out/'heldout-local-repairs.jsonl',holdout_repairs)
        jsonl(out/'generator-inputs.jsonl',input_records)
        save(out/'heldout-receipt.json',{'hypothesis_commit':commit,'cross_gate':challenge,'literary':literary_challenge,
            'blinding':freeze['generator_blinding_limit'],'ALCH005_sealed_data_accessed':False,
            'scientific_conclusion':'NO_NEW_STRUCTURAL_TRANSFER'})
        save(out/'controls.json',{'sources':controls,'literal_line_permutation':line_control,'known_gate6':{'status':known['status'],
            'counterexample':known['counterexample'],'new_discovery':False,'network_realizations':network_witness}})
        save(out/'baseline-comparison.json',{'sources':baselines,'selection':'Pareto, ties retained',
            'new_independent_transfers':{'A':0,'B':0,'C':0,'D':0},'LLM':'NOT_RUN'})
        controls_ok=line_control['status']=='PASS' and all(x['alpha_target']=='PASS' and x['alpha_source_identifiers']=='PASS' and
            x['sequence']['status'] in ['PASS','NOT_APPLICABLE_NO_SEQUENCE_RELATION'] and
            x['contrast_deletion']['status']=='PASS' and x['role_deletion']['status'] in ['PASS','NOT_APPLICABLE_NO_ROLE_RELATION'] for x in controls)
        groups={e['name']:[m for m in models if m['source_name']==e['name'] and m['check']['status']=='FORMAL_TRANSLATION_VALID'] for e in entries}
        g1=all(len({m['observed_semantics_sha256'] for m in ms})>=2 and any(m['nontrivial_proved'] for m in ms) for ms in groups.values())
        result={'status':'STAGING_ONLY','engineering_status':'PASS' if g1 and controls_ok else 'FAIL',
            'scientific_status':'NO_NEW_STRUCTURAL_TRANSFER','gates':{'G0':'PENDING_FULL_REGRESSIONS','G1':'PASS' if g1 else 'FAIL',
                'G2':'PASS' if all(r['recheck']['status']=='FORMAL_TRANSLATION_VALID' for r in repairs) else 'FAIL',
                'G3':'FAIL_NO_NEW_STRUCTURAL_TRANSFER','G4':'PASS' if controls_ok else 'FAIL',
                'G5':'PENDING_PRIVATE_MCP','G6':'PENDING_CLEAN_EXTRACTED_REPLAY'},
            'sources':{name:{'valid_models':len(ms),'distinct_observed_semantics':len({m['observed_semantics_sha256'] for m in ms}),
                'nontrivial_formal_laws':sum(m['nontrivial_proved'] for m in ms)} for name,ms in groups.items()},
            'production_changed':False,'unknowns_preserved':True,'proof_status':'unverified','execution_permission':{'allowed':False}}
        save(out/'result.json',result);cost['wall_ms']=(time.monotonic()-start)*1000;save(out/'costs.json',cost)
        return result
    finally:trace.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    a=parser.parse_args();print(json.dumps(asyncio.run(run(a.root.resolve(),a.out.resolve())),ensure_ascii=False))
