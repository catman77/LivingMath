"""Application lifecycle on the existing atomic Workspace; immutable originals."""
from ..core import digest
from ..errors import AssuranceError
from ..service import Service,require
from .records import seal,validate
from .binder import bind,revision
from .compare import evaluate
from .assurance import assure


class SemanticService:
    def __init__(self,root):
        self.base=Service(root)

    def workspace(self,project):return self.base.workspace(project)

    @staticmethod
    def known(rows,action,key,ref):
        if not any(r['action']==action and r['result'].get(key)==ref for r in rows):
            raise AssuranceError('REFERENCE_NOT_IN_PROJECT', '/'+key)

    def edition(self,project,source_ref,metadata,actor,reason,request_key):
        require(isinstance(reason,str) and bool(reason.strip()),'EDITION_SCOPE_REVIEW_REQUIRED')
        require(isinstance(actor,str) and bool(actor.strip()),'REVIEW_ACTOR_REQUIRED')
        expected={'author','title','edition','editorial_source_url','edition_status'}
        require(isinstance(metadata,dict) and set(metadata)==expected,'EDITION_METADATA_FIELDS_REQUIRED')
        w=self.workspace(project);payload={'source_ref':source_ref,'metadata':metadata,'actor':actor,'reason':reason}
        def save(rows):
            self.known(rows,'source.add','source_ref',source_ref);a=w.get(source_ref);source=a['snapshot']
            value=seal('source-edition',project,digest(source),{'source_ref':source_ref,'source_sha256':source['sha256'],
                'source_id':source['source_id'],**metadata,'rights':source['rights'],'publication_policy':a['publication_policy'],
                'provenance':{'method':'OWNER_DECLARED_EDITION_OVER_EXACT_SOURCE','editorial_authenticity_certified':False},
                'scope':'Pinned transcription only; literal quotes and unverified literary interpretation; no execution.',
                'owner_review_reason':reason},origin='TRUSTED_CONTEXT',producer=digest(payload),created_by=actor,parents=[source_ref])
            ref=w.put(value)
            return {'edition_ref':ref,'source_ref':source_ref,'status':'ACCEPT_SOURCE','execution_permission':False},[ref]
        return w.transact('semantic.edition',request_key,payload,save)

    def import_proposal(self,project,edition_ref,raw,request_key,*,parents=(),mode='MANUAL',operation='REFINE',merge_resolution=''):
        require(mode in ('MANUAL','FIXTURE'),'HOSTED_PROVENANCE_NOT_CLIENT_ASSIGNABLE')
        receipt={'backend':mode,'raw_output_sha256':__import__('hashlib').sha256(raw.encode()).hexdigest(),
                 'model_invoked':False,'model_version':'NOT_APPLICABLE','usage':None,'cost_USD':None}
        return self._register(project,edition_ref,raw,request_key,parents=parents,mode=mode,receipt=receipt,
                              operation=operation,merge_resolution=merge_resolution)

    def _register(self,project,edition_ref,raw,request_key,*,parents=(),mode,receipt,operation='REFINE',merge_resolution=''):
        w=self.workspace(project)
        require(isinstance(raw,str),'JSON_TEXT_REQUIRED')
        payload={'edition_ref':edition_ref,'raw':raw,'parents':list(parents),'mode':mode,'receipt':receipt,
                 'operation':operation,'merge_resolution':merge_resolution}
        key='sb-proposal:'+digest(request_key)
        def save(rows):
            self.known(rows,'semantic.edition','edition_ref',edition_ref);edition=w.get(edition_ref)
            for ref in parents:
                self.known(rows,'semantic.bind','frame_ref',ref)
                require(not any(r['action']=='semantic.withdraw' and r['result']['frame_ref']==ref for r in rows),
                        'WITHDRAWN_PARENT_REQUIRES_NEW_BRANCH_REVIEW')
            record=seal('proposal-record',project,edition['source_snapshot_digest'],{
                'edition_ref':edition_ref,'raw_proposal':raw,'generation_mode':mode,
                'model_version_or_unknown':receipt.get('model_version','UNKNOWN'),'receipt':receipt,
                'registration_state':'FRAME_UNTRUSTED','phase':'revise' if parents else 'initial',
                'parent_frames':list(parents),'operation':operation if parents else 'ADD','merge_resolution':merge_resolution},
                origin=mode,producer=digest(receipt),parents=parents)
            ref=w.put(record)
            return {'proposal_ref':ref,'status':'FRAME_UNTRUSTED','execution_permission':False},[ref]
        proposed=w.transact('semantic.propose',key,payload,save)
        return self.finish(project,proposed['proposal_ref'])

    def finish(self,project,proposal_ref):
        w=self.workspace(project)
        def build(rows):
            self.known(rows,'semantic.propose','proposal_ref',proposal_ref);record=w.get(proposal_ref)
            edition=w.get(record['edition_ref']);source=w.get(edition['source_ref'])['snapshot']
            parents=[w.get(ref) for ref in record['parent_frames']]
            try:
                frame,anchors,proposed=bind(record,record['edition_ref'],edition,source,parents)
                refs=[w.put(a) for a in anchors.values()];frame_ref=w.put(frame);refs.append(frame_ref);edge_ref=None
                if parents:
                    edge=revision(record,frame_ref,frame,parents,anchors,proposed);edge_ref=w.put(edge);refs.append(edge_ref)
                return {'proposal_ref':proposal_ref,'frame_ref':frame_ref,'edge_ref':edge_ref,
                        'anchor_refs':sorted(anchors),'status':'FRAME_REVISED' if parents else 'FRAME_VALIDATED',
                        'validation_state':'FRAME_VALIDATED','execution_permission':False},refs
            except AssuranceError as exc:
                failure=seal('failure',project,edition['source_snapshot_digest'],{
                    'proposal_ref':proposal_ref,'reason_code':exc.code,'field':exc.field,
                    'registration_state':'FRAME_UNTRUSTED','preflight_decision':'REJECTED'},producer=record['producer_ref'],parents=[proposal_ref])
                ref=w.put(failure)
                return {'proposal_ref':proposal_ref,'failure_ref':ref,'status':'FRAME_UNTRUSTED',
                        'reason_code':exc.code,'preflight_decision':'REJECTED','execution_permission':False},[ref]
        result=w.transact('semantic.bind','sb-bind:'+proposal_ref,{'proposal_ref':proposal_ref},build)
        if 'frame_ref' not in result:return result
        frame_ref=result['frame_ref'];frame=w.get(frame_ref);edition=w.get(frame['poem_ref']);source=w.get(edition['source_ref'])['snapshot']
        anchors={ref:w.get(ref) for ref in result['anchor_refs']}
        value=assure(self.base,project,frame_ref,frame,edition,source,anchors)
        def save(rows):
            ref=w.put(value)
            return {'frame_ref':frame_ref,'assurance_ref':ref,'status':'UNKNOWN','execution_permission':False},[ref]
        assurance=w.transact('semantic.assure','sb-assure:'+frame_ref,{'frame_ref':frame_ref},save)
        return {**result,'assurance_ref':assurance['assurance_ref'],'epistemic_status':'UNKNOWN'}

    def compare(self,project,left_ref,right_ref,fields,queries,request_key,*,complete=True,expectation='REPORT',loss_origin='DECLARED_ANNOTATION'):
        w=self.workspace(project);payload={'left':left_ref,'right':right_ref,'fields':fields,'Q':queries,'complete':complete,
                                         'expectation':expectation,'loss_origin':loss_origin}
        def run(rows):
            for ref in (left_ref,right_ref):self.known(rows,'semantic.bind','frame_ref',ref)
            left,right=w.get(left_ref),w.get(right_ref)
            domain=list(dict.fromkeys([left_ref,right_ref]))
            contract=seal('projection',project,left['source_snapshot_digest'],{
                'left_ref':left_ref,'right_ref':right_ref,'projection_fields':fields,'declared_Q':queries,
                'Q_complete':complete,'domain_refs':domain,'expectation':expectation,'loss_origin':loss_origin},
                producer=digest(payload),parents=domain)
            ref=w.put(contract);witness=evaluate(contract,left,right,ref);wref=w.put(witness)
            return {'projection_ref':ref,'witness_ref':wref,'status':witness['status'],
                    'reason_code':witness['reason_code'],'execution_permission':False},[ref,wref]
        return w.transact('semantic.compare',request_key,payload,run)

    def withdraw(self,project,frame_ref,reason,request_key):
        require(isinstance(reason,str) and bool(reason.strip()),'WITHDRAWAL_REASON_REQUIRED')
        w=self.workspace(project)
        def run(rows):
            self.known(rows,'semantic.bind','frame_ref',frame_ref);frame=w.get(frame_ref)
            value=seal('withdrawal',project,frame['source_snapshot_digest'],{'frame_ref':frame_ref,'reason':reason,
                'registration_state':'FRAME_WITHDRAWN'},producer=digest({'actor':'owner','reason':reason}),parents=[frame_ref])
            ref=w.put(value)
            return {'frame_ref':frame_ref,'withdrawal_ref':ref,'status':'FRAME_WITHDRAWN','execution_permission':False},[ref]
        return w.transact('semantic.withdraw',request_key,{'frame_ref':frame_ref,'reason':reason},run)
