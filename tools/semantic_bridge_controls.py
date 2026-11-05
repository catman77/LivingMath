"""Declared manual structural controls, kept separate from actual model readings."""
import json
from pathlib import Path
from lm_suti_assurance.core import canonical
from lm_suti_assurance.semantic_bridge.service import SemanticService


def run(state,project):
    s=SemanticService(state);w=s.workspace(project);rows=w.history()
    editions={r['result']['edition_ref']:w.get(r['result']['edition_ref']) for r in rows if r['action']=='semantic.edition'}
    actual=[w.get(r['result']['frame_ref']) for r in rows if r['action']=='semantic.bind' and 'frame_ref' in r['result'] and w.get(r['result']['frame_ref'])['generation_mode']=='HOSTED_MODEL']
    frames={ref:[] for ref in editions}
    for r in rows:
        if r['action']=='semantic.bind' and 'frame_ref' in r['result']:
            f=w.get(r['result']['frame_ref'])
            if f['generation_mode']=='HOSTED_MODEL':frames[f['poem_ref']].append(r['result']['frame_ref'])
    output=[]
    for ed,refs in frames.items():
        if len(refs)!=2:continue
        spec=[{'id':'order','kind':'STRUCTURAL_FIELD','field':'/image_order','question':'Declared image order'},
              {'id':'details','kind':'STRUCTURAL_FIELD','field':'/canal_details','question':'Declared canal details'}]
        output.append(s.compare(project,refs[0],refs[1],['/image_set'],spec,'actual-comparison:'+ed))
    ed=next(ref for ref,e in editions.items() if e['source_id']=='blok_night_1960');model=next(f for f in actual if f['poem_ref']==ed)
    proposal=json.loads(w.get(model['raw_proposal_ref'])['raw_proposal'])
    proposal['literal_observations']=[{'id':'literal-first','text':'Декларируется первая строка.','quote':'Ночь, улица, фонарь, аптека,'},
                                     {'id':'literal-end','text':'Декларируется строка о канале.','quote':'Ночь, ледяная рябь канала,'}]
    # Retain valid relation IDs after replacing the literal-atom identifiers.
    old_ids={c['id'] for c in proposal['interpretations']}
    for r in proposal['relations']:
        if r['from_claim'] not in old_ids:r['from_claim']='literal-first'
        if r['to_claim'] not in old_ids:r['to_claim']='literal-end'
    proposal['observables']={'image_set':['ночь','улица','фонарь','аптека','канал'],'image_order':['ночь','улица','фонарь','аптека'],
                            'canal_details':[],'speaker_roles':[]}
    proposal['revision_rationale']='FIXTURE: first declared structural annotation, not an additional model reading.'
    first=s.import_proposal(project,ed,canonical(proposal),'manual-structural-first',mode='FIXTURE')
    proposal['observables']['image_order']=['ночь','канал','аптека','улица','фонарь'];proposal['observables']['canal_details']=['ледяная рябь канала']
    proposal['revision_rationale']='FIXTURE: second declared structural annotation, independently chosen finite loss control.'
    second=s.import_proposal(project,ed,canonical(proposal),'manual-structural-second',mode='FIXTURE')
    q=[{'id':'order','kind':'STRUCTURAL_FIELD','field':'/image_order','question':'Exact proposed annotation image order'},
       {'id':'canal','kind':'STRUCTURAL_FIELD','field':'/canal_details','question':'Exact proposed annotation canal detail'}]
    loss=s.compare(project,first['frame_ref'],second['frame_ref'],['/image_set'],q,'manual-loss-control')
    rejected=s.compare(project,first['frame_ref'],second['frame_ref'],['/image_set'],q,'false-preservation-control',expectation='PRESERVED_FOR_DECLARED_Q')
    no_loss=s.compare(project,first['frame_ref'],second['frame_ref'],['/image_set','/image_order','/canal_details'],q,'full-projection-control')
    unspecified=s.compare(project,first['frame_ref'],second['frame_ref'],['/image_set'],[],'missing-Q-control')
    conjecture=s.compare(project,first['frame_ref'],second['frame_ref'],['/image_set'],[{'id':'world','kind':'SEMANTIC_QUESTION','field':'','question':'Does the actual physical world return to numerical identity?'}],'semantic-question-control')
    assert loss['status']=='LOSS_DETECTED' and rejected['status']=='REJECTED' and no_loss['status']=='PRESERVED_FOR_DECLARED_Q'
    return {'actual_model_pairs':output,'fixture_frames':[first,second],'loss':loss,'false_preservation':rejected,'no_loss':no_loss,
            'missing_Q':unspecified,'semantic_conjecture':conjecture,'fixture_counts_as_model_reading':False}


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--state',type=Path,required=True);p.add_argument('--project',default='semantic-poetry-001');p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=run(a.state,a.project);a.output.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print('PASS_ACTUAL_PAIRS_AND_MANUAL_STRUCTURAL_CONTROLS')
