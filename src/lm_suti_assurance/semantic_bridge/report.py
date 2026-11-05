"""A research dossier of competing proposed readings, not a canonical meaning."""
import html
from ..core import digest,canonical
from ..service import require
from .records import seal

BOUNDARY=('SOURCE_ATTESTED certifies exact quote-envelope bytes after UTF-8 source preflight, not interpretive prose. '
          'Interpretations remain UNKNOWN/HOLD. Structural loss covers declared annotations and finite Q/domain only. '
          'No native SUTI, formal/physical truth or execution grant. R3=PENDING.')


def dossier(workspace,rows=None):
    if rows is None:
        with workspace.locked():return dossier(workspace,workspace.history())
    editions=[];frames=[];edges=[];proposals=[];assurances=[];comparisons=[];withdrawals=[];failures=[]
    for r in rows:
        action=r['action'];v=r['result']
        if action=='semantic.edition':editions.append(v['edition_ref'])
        elif action=='semantic.propose':proposals.append(v['proposal_ref'])
        elif action=='semantic.bind':
            if 'frame_ref' in v:
                frames.append(v['frame_ref'])
                if v.get('edge_ref'):edges.append(v['edge_ref'])
            else:failures.append(v['failure_ref'])
        elif action=='semantic.assure':assurances.append(v['assurance_ref'])
        elif action=='semantic.compare':comparisons.append(v['witness_ref'])
        elif action=='semantic.withdraw':withdrawals.append(v['withdrawal_ref'])
    require(bool(rows),'PROJECT_NOT_FOUND')
    srcs=sorted({workspace.get(r)['source_snapshot_digest'] for r in editions})
    header=seal('dossier',workspace.project,None,{'frame_refs':frames,'edition_refs':editions,
        'revision_edge_refs':edges,'comparison_refs':comparisons,'assurance_refs':assurances,
        'raw_proposal_refs':proposals,'receipt_refs':proposals,'source_snapshot_digests':srcs,
        'R3':'PENDING','boundary':BOUNDARY},producer=digest({'journal_head':rows[-1]['hash']}),parents=frames)
    def get_all(refs):return [{'ref':ref,'value':workspace.get(ref)} for ref in refs]
    anchor_refs=sorted({ref for f in frames for c in workspace.get(f)['claim_atoms'] for ref in c['source_anchor_refs']} |
                       {ref for f in frames for r in workspace.get(f)['relations'] for ref in r['source_anchor_refs']} |
                       {ref for f in frames for m in workspace.get(f)['motifs'] for ref in m['source_anchor_refs']})
    return {'dossier':header,'editions':get_all(editions),'frames':get_all(frames),'revision_edges':get_all(edges),
            'anchors':get_all(anchor_refs),'assurances':get_all(assurances),'comparisons':get_all(comparisons),
            'proposals_and_receipts':get_all(proposals),'withdrawals':get_all(withdrawals),'failures':get_all(failures),
            'current_registration_states':{ref:'FRAME_WITHDRAWN' if any(workspace.get(w)['frame_ref']==ref for w in withdrawals)
                                             else 'FRAME_REVISED' if workspace.get(ref)['parent_refs'] else 'FRAME_VALIDATED' for ref in frames},
            'journal_head':rows[-1]['hash'],'boundary':BOUNDARY,'execution_permission':False}


def markdown(value):
    lines=['# История исследовательских прочтений','',BOUNDARY,'',
           '| Источник | Версия | Происхождение | Workflow | Смысловой статус |','|---|---:|---|---|---|']
    editions={x['ref']:x['value'] for x in value['editions']}
    for row in value['frames']:
        f=row['value'];title=html.escape(editions[f['poem_ref']]['title']).replace('|','&#124;')
        lines.append('| '+title+' | '+str(f['revision_index'])+' | '+f['generation_mode']+' | '+value['current_registration_states'][row['ref']]+' | UNKNOWN |')
    for row in value['frames']:
        f=row['value'];lines+=['','## '+html.escape(editions[f['poem_ref']]['title'])+' — версия '+str(f['revision_index']),
            '', 'Предложенное временное прочтение: '+f['temporal_reading']+'.', '', 'Содержательные гипотезы:']
        lines += ['- '+html.escape(c['text'])+' ['+c['kind']+'; '+c['epistemic_status']+']' for c in f['claim_atoms']]
        lines += ['', 'Альтернативы:']+['- '+html.escape(v) for v in f['counterreadings']]
        lines += ['', 'Ограничения / открытые вопросы:']+['- '+html.escape(v) for v in f['limitations']+f['open_questions']]
    lines+=['','## Машиночитаемые исходные опоры, изменения и проверки','',
            'Полные source anchors, RevisionEdge, raw proposals/receipts и проверяемые loss witnesses сохранены в dossier.json.', '']
    return '\n'.join(lines)
