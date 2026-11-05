"""Additive CLI commands with explicit source scope and untrusted proposals."""
import json
from pathlib import Path
from ..core import canonical,digest
from ..errors import AssuranceError
from ..validation import parse
from ..workspace import atomic_write
from .service import SemanticService
from .report import dossier,markdown
from .bundle import export


def add_parser(sub):
    p=sub.add_parser('semantic');actions=p.add_subparsers(dest='semantic_action',required=True)
    for name in ('source','draft','revise','import','compare','report','withdraw'):
        a=actions.add_parser(name);a.add_argument('--project',required=True)
        if name!='report':a.add_argument('--request-key',required=True)
        if name=='source':
            a.add_argument('--source-ref',required=True);a.add_argument('--metadata',required=True)
            a.add_argument('--actor',required=True);a.add_argument('--reason',required=True)
        elif name in ('draft','import'):
            a.add_argument('--source-ref',dest='edition_ref',required=True,help='Pinned semantic SourceEdition ref')
            a.add_argument('--proposal');a.add_argument('--private',help='Private hosted-proposer receipts directory')
            a.add_argument('--phase',choices=['initial'],default='initial')
        elif name=='revise':
            a.add_argument('--frame-ref',required=True);a.add_argument('--challenge',required=True)
            a.add_argument('--proposal');a.add_argument('--private')
        elif name=='compare':
            a.add_argument('--left',required=True);a.add_argument('--right',required=True)
            a.add_argument('--projection',required=True,help='JSON file: fields, declared_Q, complete, expectation')
        elif name=='withdraw':a.add_argument('--frame-ref',required=True);a.add_argument('--reason',required=True)
        elif name=='report':a.add_argument('--output');a.add_argument('--format',choices=['json','markdown'],default='markdown')


def run(args):
    s=SemanticService(args.state_dir);action=args.semantic_action;p=args.project
    def read(path):return parse(Path(path).read_text())
    if action=='source':return s.edition(p,args.source_ref,read(args.metadata),args.actor,args.reason,args.request_key)
    if action in ('draft','revise','import'):
        w=s.workspace(p);parents=[];initial=None
        if action=='revise':
            with w.locked():
                rows=w.history();s.known(rows,'semantic.bind','frame_ref',args.frame_ref);initial=w.get(args.frame_ref)
            edition_ref=initial['poem_ref'];parents=[args.frame_ref]
        else:edition_ref=args.edition_ref
        if args.proposal:
            return s.import_proposal(p,edition_ref,Path(args.proposal).read_text(),args.request_key,parents=parents)
        if action=='import':raise AssuranceError('PROPOSAL_FILE_REQUIRED')
        with w.locked():
            rows=w.history();s.known(rows,'semantic.edition','edition_ref',edition_ref)
            # Resume a completed caller request before invoking a hosted generator.
            prior=next((r for r in rows if r['action']=='semantic.propose' and r['request_key']=='sb-proposal:'+digest(args.request_key)),None)
            if prior:
                record=w.get(prior['result']['proposal_ref'])
                if (record['edition_ref']!=edition_ref or record['parent_frames']!=parents
                        or record['receipt'].get('request',{}).get('diagnostic_question')!=(args.challenge if parents else None)):
                    raise AssuranceError('REQUEST_KEY_CONFLICT')
            edition=w.get(edition_ref);source=w.get(edition['source_ref'])['snapshot']
        if prior:return s.finish(p,prior['result']['proposal_ref'])
        from .proposer import generate
        private=Path(args.private) if args.private else w.root/'.model-receipts'
        receipt=generate(source,edition,'revise' if parents else 'initial',initial,args.challenge if parents else None,
                         private,p+':'+args.request_key)
        value=s._register(p,edition_ref,receipt['raw_output'],args.request_key,parents=parents,mode='HOSTED_MODEL',receipt=receipt)
        if receipt['status']!='OK':value={**value,'model_status':receipt['status'],'status':'MODEL_UNAVAILABLE'}
        return value
    if action=='compare':
        spec=read(args.projection)
        return s.compare(p,args.left,args.right,spec['fields'],spec['declared_Q'],args.request_key,
            complete=spec.get('complete',True),expectation=spec.get('expectation','REPORT'),loss_origin=spec.get('loss_origin','DECLARED_ANNOTATION'))
    if action=='withdraw':return s.withdraw(p,args.frame_ref,args.reason,args.request_key)
    value=dossier(s.workspace(p))
    if args.output:
        path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True)
        atomic_write(path,(canonical(value) if args.format=='json' else markdown(value)).encode())
        return {'status':'EXPORTED_REPORT','dossier_digest':value['dossier']['content_digest'],'execution_permission':False}
    return value
