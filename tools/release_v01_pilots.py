"""Prepare the three R3 cases. Automated preparation is not external-human evidence."""
import argparse
import json
from pathlib import Path
from lm_suti_assurance import core
from lm_suti_assurance.core import canonical
from lm_suti_assurance.service import Service
from lm_suti_assurance.bundle import export_bundle,replay
from lm_suti_assurance.report import report,text_report
from lm_suti_assurance.smoke import POLICY,TAG


def build(state,output):
    service=Service(state);output.mkdir(parents=True,exist_ok=True)
    tasks=json.loads((core.ROOT/'examples/FROZEN_CORPUS.json').read_text())
    sources=json.loads((core.ROOT/'examples/SOURCE_SNAPSHOTS.json').read_text())
    matrix=[('source-projection',[
        ('S1',{'kind':'SOURCE_PROJECTION','relation':'LOSS_DETECTED'},'SOURCE_ATTESTED'),
        ('S1',{'kind':'SOURCE_PROJECTION','relation':'PRESERVED_FOR_DECLARED_Q'},'REJECTED')]),
        ('finite-counterexample',[
        ('F2',{'kind':'FINITE_TRACE','trace':[1]*4,'strength':'ENTAILED'},'CHECKED_FINITE'),
        ('F1',{'kind':'FINITE_TRACE','trace':[0]*6,'strength':'ENTAILED'},'REJECTED')]),
        ('bounded-invariant',[
        ('C1',{'kind':'BOUNDED_PROPERTY','property':'PRESERVES_POPCOUNT'},'CHECKED_FINITE'),
        ('C1',{'kind':'BOUNDED_PROPERTY','property':'PRESERVES_VALUE'},'REJECTED')])]
    summary=[]
    for project,cases in matrix:
        service.new(project,'new');taskrefs={};compiled=None;results=[]
        for index,(tid,delta,expected) in enumerate(cases):
            task=tasks[tid]
            for sid in task['source_ids']:service.source(project,sources[sid],POLICY,'source.'+sid)
            tr=service.task(project,{'schema':'lm-suti.assurance.task/0.1','project':project,'task':task},'task.'+tid)
            service.review(project,tr['task_ref'],'QA_OPERATOR','Automated pilot preparation. Independent human replay still required.','review.'+tid)
            a={'schema':'lm-suti.assurance.candidate/0.1','project':project,'task_ref':tr['task_ref'],
               'format':'delta','raw':canonical({'schema':TAG,'intent':'PROPOSE',**delta})}
            c=service.candidate(project,a,'candidate.'+str(index));d=service.check(project,c['candidate_ref'],'direct','check.'+str(index))
            assert d['status']==expected,(project,d,expected);results.append(d)
            if index==0:
                compiled=service.workspace(project).get(d['check_ref'])['candidate']
                unknown_task_ref=tr['task_ref']
        unknown={**compiled,'candidate_id':'unknown-proposal','assertion':{**compiled['assertion'],'machine_term':None,'content':'null'}}
        a={'schema':'lm-suti.assurance.candidate/0.1','project':project,'task_ref':unknown_task_ref,'format':'candidate','raw':canonical(unknown)}
        c=service.candidate(project,a,'candidate.unknown');d=service.check(project,c['candidate_ref'],'direct','check.unknown')
        assert d['status']=='HOLD' and d['reason_code']=='MACHINE_TERM_MISSING';results.append(d)
        raw,manifest=export_bundle(service.workspace(project),'reviewers');r=replay(raw)
        (output/(project+'.zip')).write_bytes(raw)
        (output/(project+'-report.txt')).write_text(text_report(report(service.workspace(project))))
        summary.append({'project':project,'results':results,'replay':r,'sha256':core.byte_digest(raw),
                        'external_human_replay':'PENDING'})
    (output/'PILOT_CASES.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':'PREPARED','projects':[v['project'] for v in summary],'external_human_testers_completed':0}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--state',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();build(a.state,a.output)
