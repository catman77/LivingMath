"""The preregistered 3 texts × 2 consecutive hosted readings; no quality retry."""
import argparse,json
from pathlib import Path
from lm_suti_assurance import core
from lm_suti_assurance.service import Service
from lm_suti_assurance.semantic_bridge.service import SemanticService
from lm_suti_assurance.semantic_bridge.proposer import generate

CHALLENGES={
 'blok_night_1960':'Что в источнике поддерживает и что ограничивает утверждение о тождестве мира? Различите порядок образов, повторение и возможные альтернативные временные прочтения. Не считайте вопрос готовым ответом.',
 'pushkin_anchar_1956':'Не подменяет ли прочтение власти и насилия утверждение о реальной физической причинности? Проверьте последовательность действия, возможные роли агентов и конкурирующие трактовки.',
 'pushkin_loved_1948':'Как различаются сообщение о чувстве и речевой акт отказа тревожить адресата? Какие альтернативы остаются и какие биографические мотивы источник не устанавливает?'}
POLICY={'schema':'lm-suti.assurance.publication-policy/0.1','audiences':['private'],'allow_source_bytes':True,
        'reason':'Owner supplied this corpus for private semantic-bridge QA; no public publication authorized.'}


def run(state,private,audit_path,project):
    private.mkdir(mode=0o700,parents=True,exist_ok=True)
    audit=json.loads(audit_path.read_text());base=Service(state);semantic=SemanticService(state)
    base.new(project,'sb-pilot-project');results=[]
    for entry in audit['records']:
        sid=entry['id'];snapshot=core.contracts.SourceSnapshot.create(sid,entry['raw_text_utf8'],
            'Owner-provided transcription for private semantic QA; '+entry['verification_url'],kind='qa').record
        snapshot['provenance']={'method':'EXACT_USER_FIXTURE_BYTES','edition_status':entry['edition_status'],
                                'reference_html_sha256':entry.get('reference_html_sha256'),'author_endorsement_claimed':False}
        added=base.source(project,snapshot,POLICY,'sb-source:'+sid)
        edition=semantic.edition(project,added['source_ref'],{'author':entry['author'],'title':entry['title'],
            'edition':entry['declared_edition'],'editorial_source_url':entry['verification_url'],
            'edition_status':entry['edition_status']},'OWNER_QA_SCOPE',
            'Confirm exact supplied transcription, private rights and all literal-byte/unverified-interpretation checks only.', 'sb-edition:'+sid)
        w=semantic.workspace(project);ed=w.get(edition['edition_ref']);parent_ref=None;initial=None
        for phase in ('initial','revise'):
            if phase=='revise' and parent_ref is None:
                results.append({'source_id':sid,'phase':phase,'status':'BLOCKED_INITIAL_READING_INVALID'});continue
            receipt=generate(snapshot,ed,phase,initial,CHALLENGES[sid] if phase=='revise' else None,private/'model-attempts',sid+':'+phase)
            # Retain an error receipt/raw proposal too; it never counts as a successful model reading.
            result=semantic._register(project,edition['edition_ref'],receipt['raw_output'],'sb-reading:'+sid+':'+phase+':'+receipt['request_sha256'][:12],
                parents=[parent_ref] if parent_ref else [],mode='HOSTED_MODEL',receipt=receipt)
            row={'source_id':sid,'phase':phase,'model_status':receipt['status'],**result};results.append(row)
            (private/'READING_RESULTS.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
            print(core.canonical({k:row[k] for k in ('source_id','phase','model_status','status')}),flush=True)
            if receipt['status']=='POLICY_VIOLATION':raise RuntimeError('SHUTOFF_FORBIDDEN_GENERATOR_TOOL')
            if receipt['status']=='OK' and 'frame_ref' in result and phase=='initial':
                parent_ref=result['frame_ref'];initial=w.get(parent_ref)
    return results


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('state','private','audit'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--project',default='semantic-poetry-001');a=p.parse_args();run(a.state,a.private,a.audit,a.project)
