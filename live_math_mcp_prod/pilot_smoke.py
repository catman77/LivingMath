"""No external claims: test research workflow isolation and status discipline."""
import json,tempfile
from pathlib import Path
from research_store import ResearchStore

def main():
    with tempfile.TemporaryDirectory() as td:
        s=ResearchStore(Path(td)/'pilot.sqlite3')
        scenarios=[('RH','unproved critical lemma','Investigate precise unsupported implication', 'Counterexample search required before further claims'),('SoftFTL','dynamic latent readout','Question whether data leakage exists', 'Blind holdout and negative controls are mandatory'),('ARC','representation shift','Test novel task without training-source leakage', 'Unseen tasks and predeclared scoring required')]
        out={}
        for project,focus,proposal,evidence in scenarios:
            a=s.record(project,'attention',focus,proposal,status='observation')
            b=s.record(project,'interpretation',focus,'Candidate reformulation—not established',status='hypothesis',parent_id=a['id'])
            c=s.record(project,'counterexample',focus,'Prior approach not validated; RCA pending',status='refuted',parent_id=b['id'],evidence=evidence)
            r=s.audit(project,'Replace representation while preserving original mechanism')
            out[project]={'records':len(s.events(project)), 'flags':r['warnings'],'last_status':s.events(project)[0]['status']}
        out['isolation']=s.events('RH')[0]['project']=='RH' and len(s.events('SoftFTL'))==3
        out['audit']=s.verify_audit()
        assert out['isolation'] and out['audit']['ok']
        assert all(out[p]['records']==3 for p,_,_,_ in scenarios)
        print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
