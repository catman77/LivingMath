"""Recompute saved contracts using installed code only. Never call the proposer."""
from ..core import digest,canonical,byte_digest
from ..errors import AssuranceError
from ..service import require
from .records import validate
from .binder import bind,revision
from .compare import evaluate
from .anchors import check_anchor
from .service import SemanticService


def verify_action(workspace,prior,row,project):
    result=row['result'];action=row['action'];require(result.get('execution_permission') is False,'EXECUTION_GRANT_FORBIDDEN')
    for ref in row['object_refs']:
        value=workspace.get(ref)
        if value.get('schema','').startswith('lm-suti.semantic.'):
            name=value['schema'].split('lm-suti.semantic.',1)[1].split('/')[0];validate(name,value)
            require(value['project_id']==project,'CROSS_PROJECT_REFERENCE')
    known=SemanticService.known
    if action=='semantic.edition':
        ed=workspace.get(result['edition_ref']);known(prior,'source.add','source_ref',ed['source_ref'])
        a=workspace.get(ed['source_ref']);source=a['snapshot']
        require(ed['source_snapshot_digest']==digest(source) and ed['source_sha256']==source['sha256'] and
                ed['rights']==source['rights'] and ed['publication_policy']==a['publication_policy'],'EDITION_SOURCE_BINDING_MISMATCH')
    elif action=='semantic.propose':
        record=workspace.get(result['proposal_ref']);known(prior,'semantic.edition','edition_ref',record['edition_ref'])
        for parent in record['parent_frames']:
            known(prior,'semantic.bind','frame_ref',parent)
            require(not any(r['action']=='semantic.withdraw' and r['result']['frame_ref']==parent for r in prior),'WITHDRAWN_PARENT_REQUIRES_NEW_BRANCH_REVIEW')
        if record['generation_mode']=='HOSTED_MODEL':
            receipt=record['receipt'];require(receipt.get('raw_output')==record['raw_proposal'] and
                receipt.get('raw_output_sha256')==byte_digest(record['raw_proposal'].encode()),'MODEL_RECEIPT_OUTPUT_MISMATCH')
            require(not any(e.get('item',{}).get('type') not in {None,'agent_message','reasoning','error'} for e in receipt.get('events',[])),
                    'GENERATOR_POLICY_VIOLATION')
    elif action=='semantic.bind':
        known(prior,'semantic.propose','proposal_ref',result['proposal_ref']);record=workspace.get(result['proposal_ref'])
        ed=workspace.get(record['edition_ref']);source=workspace.get(ed['source_ref'])['snapshot']
        parents=[workspace.get(ref) for ref in record['parent_frames']]
        try:frame,anchors,proposed=bind(record,record['edition_ref'],ed,source,parents)
        except AssuranceError as exc:
            require(result.get('reason_code')==exc.code and 'frame_ref' not in result,'REPLAY_BIND_FAILURE_MISMATCH')
            return
        require(digest(frame)==result.get('frame_ref') and workspace.get(result['frame_ref'])==frame,'FRAME_REPLAY_MISMATCH')
        require(sorted(anchors)==result['anchor_refs'],'ANCHOR_SET_MISMATCH')
        for ref,value in anchors.items():
            require(workspace.get(ref)==value,'SOURCE_ANCHOR_MISMATCH');check_anchor(value,source,record['edition_ref'])
        if parents:
            edge=revision(record,result['frame_ref'],frame,parents,anchors,proposed)
            require(digest(edge)==result['edge_ref'] and workspace.get(result['edge_ref'])==edge,'REVISION_EDGE_MISMATCH')
    elif action=='semantic.assure':
        known(prior,'semantic.bind','frame_ref',result['frame_ref']);frame=workspace.get(result['frame_ref']);a=workspace.get(result['assurance_ref'])
        require(a['frame_ref']==result['frame_ref'],'ASSURANCE_FRAME_MISMATCH')
        atoms={c['id']:c for c in frame['claim_atoms']};require({c['claim_id'] for c in a['claims']}==set(atoms),'ASSURANCE_CLAIM_SET_MISMATCH')
        for claim in a['claims']:
            atom=atoms[claim['claim_id']]
            if atom['kind']=='FORMAL_STRUCTURE':
                require(claim['status']=='HOLD' and claim['check_ref'] is None,'INTERPRETATION_STATUS_PROMOTION');continue
            known(prior,'check','check_ref',claim['check_ref']);checked=workspace.get(claim['check_ref']);candidate=checked['candidate']
            term=candidate['assertion']['machine_term'];ed=workspace.get(frame['poem_ref']);source=workspace.get(ed['source_ref'])['snapshot']
            require(candidate['scope']['source_snapshots'].get(source['source_id'])==digest(source),'ASSURANCE_SOURCE_UNBOUND')
            require(claim['status']==checked['status'],'ASSURANCE_RESULT_MISMATCH')
            if atom['kind']=='LITERAL':
                anchor=workspace.get(atom['source_anchor_refs'][0]);check_anchor(anchor,source,frame['poem_ref'])
                require(claim['target']=='SOURCE_QUOTE_BYTES_ONLY' and term.get('value')==anchor['quote_utf8'] and
                        term.get('predicate')=='field_equals' and term.get('pointer')=='/quote_utf8','QUOTE_ASSURANCE_UNBOUND')
            else:
                require(claim['target']=='INTERPRETATION_HYPOTHESIS' and claim['status'] in ('UNKNOWN','HOLD','CONDITIONAL_HYPOTHESIS')
                        and term.get('predicate')=='hypothesis' and term.get('text')==atom['text'],'INTERPRETATION_STATUS_PROMOTION')
    elif action=='semantic.compare':
        contract=workspace.get(result['projection_ref'])
        for ref in (contract['left_ref'],contract['right_ref']):known(prior,'semantic.bind','frame_ref',ref)
        value=evaluate(contract,workspace.get(contract['left_ref']),workspace.get(contract['right_ref']),result['projection_ref'])
        require(workspace.get(result['witness_ref'])==value and result['status']==value['status'],'STRUCTURAL_WITNESS_MISMATCH')
    elif action=='semantic.withdraw':
        known(prior,'semantic.bind','frame_ref',result['frame_ref']);withdraw=workspace.get(result['withdrawal_ref'])
        require(withdraw['frame_ref']==result['frame_ref'] and result['status']=='FRAME_WITHDRAWN','WITHDRAWAL_MISMATCH')
    else:raise AssuranceError('UNKNOWN_SEMANTIC_ACTION')


def verify_graph(objects):
    frames={ref:v for ref,v in objects.items() if v.get('schema')=='lm-suti.semantic.frame/1'}
    visiting=set();done=set()
    def walk(ref):
        if ref in visiting:raise AssuranceError('LINEAGE_CYCLE')
        if ref in done:return
        require(ref in frames,'LINEAGE_PARENT_MISSING');visiting.add(ref)
        for parent in frames[ref]['parent_refs']:walk(parent)
        visiting.remove(ref);done.add(ref)
    for ref in frames:walk(ref)
