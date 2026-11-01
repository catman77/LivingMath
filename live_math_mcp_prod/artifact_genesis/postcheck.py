"""Independent post-holdout source proxy, without proposer or target imports."""
import json
from pathlib import Path
import re
import resource
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from artifact_genesis.contract import RawPacket  # noqa: E402
from davcore.ast import digest  # noqa: E402


def check_predictions(packet: RawPacket,predictions: list[dict]) -> list[dict]:
    rows=packet.spans;text='\n'.join(s.text for s in rows);result=[]
    for p in predictions:
        if p['language']!=packet.language:continue
        kind=p['source_relation'];supported=False;witnesses=[];roles=[]
        if kind=='explicit_conditional':
            for span in rows:
                m=re.match(r'^\s*(?:If|Если)\s+(.+?),\s*(.+)',span.text,re.I)
                if m:
                    supported=True;witnesses=[span];roles=[{'role':'antecedent','quote':m.group(1)},{'role':'consequent','quote':m.group(2)}];break
        elif kind=='ordered_parallel_role_reversal':
            ordered=bool(re.search(r'\bfirst\b[\s\S]+\bthen\b',text,re.I))
            if ordered:witnesses=[s for s in rows if re.search(r'\b(?:first|then)\b',s.text,re.I)]
            # No lexical identity/synonym oracle: do not silently identify the four roles.
            supported=False
        elif kind=='unseen_necessity_of_conjoined_clauses':
            # A coordination marker is never sufficient source evidence of necessity.
            supported=False
        elif kind=='negated_prerequisite':
            for i,s in enumerate(rows):
                if re.search(r'\bwithout\b.+\b(?:no|may|not)\b',s.text,re.I) and i>0:
                    supported=True;witnesses=[rows[i-1],s];roles=[{'role':'antecedent_event','quote':rows[i-1].text},
                        {'role':'negated_outcome_without_antecedent','quote':s.text}];break
        elif kind=='contrasted_method_with_explicit_order':
            rejection=re.search(r'\b(?:not|no|never)\b',text,re.I)
            ordering=re.search(r'\bfirst\b[\s\S]+\bthen\b',text,re.I)
            agency=re.search(r'\b(?:we|thou|they|our)\b',text,re.I)
            supported=bool(rejection and ordering and agency)
            if supported:witnesses=[s for s in rows if re.search(r'\b(?:not|first|then|we|thou)\b',s.text,re.I)]
        elif kind=='new_subject_acts_on_former_addressee':
            # Independent case-form proxy across a continued pair of verse lines; no noun dictionary.
            for i,s in enumerate(rows):
                m=re.match(r'^\s*И\s+([^\W\d_]+)\b',s.text,re.I)
                if m and m.group(1).casefold() not in {'ты','я','он','она','мы','вы'}:
                    tail=rows[i+1] if i+1<len(rows) else s
                    if re.search(r'\bтебя\b',s.text+' '+tail.text,re.I):
                        supported=True;witnesses=[s,tail];roles=[{'role':'new_explicit_subject_form','quote':m.group(1)},
                            {'role':'former_addressee_as_object','quote':'тебя'}];break
        verdict='PROXY_MATCH' if supported else 'REQUIRES_SEMANTIC_REVIEW' if kind=='ordered_parallel_role_reversal' and witnesses else 'FAIL_NO_SOURCE_MATCH'
        result.append({'prediction_id':p['id'],'packet_id':packet.id,'source_relation':kind,
            'status':verdict,
            'quoted_evidence':[{'span_id':s.id,'start':s.start,'end':s.end,'quote':s.text} for s in witnesses],
            'observed_role_bindings':roles,'document_sha256':packet.document_sha256,'edition':packet.edition,
            'novelty_status':'INSTANCE_OF_BOUNDED_GRAMMATICAL_SCHEMA_NOT_AN_INDEPENDENT_NEW_LAW' if supported else 'PREDICTION_NOT_CONFIRMED',
            'semantic_review':'SEMANTIC_NOT_EXTERNALLY_REVIEWED','target_result_used':False,
            'new_scientific_relation_verified':False,'proof_status':'unverified','execution_permission':{'allowed':False}})
    return result


def main():
    raw=sys.stdin.buffer.read(64001)
    if len(raw)>64000:raise ValueError('POSTCHECK_INPUT_BOUND')
    req=json.loads(raw)
    if set(req)!={'packet','predictions','seal'}:raise ValueError('TARGET_OR_ANSWER_NOT_ALLOWED_IN_POSTCHECK')
    if digest(req['predictions'])!=req['seal']['prediction_sha256']:raise ValueError('PREDICTION_SEAL_MISMATCH')
    packet=RawPacket.model_validate(req['packet'])
    resource.setrlimit(resource.RLIMIT_CPU,(5,5));resource.setrlimit(resource.RLIMIT_FSIZE,(0,0))
    def deny(event,args):
        if event in {'open','os.listdir','os.scandir','subprocess.Popen','os.system','ctypes.dlopen'} or event.startswith('socket.'):
            raise PermissionError('POSTCHECK_EXTERNAL_IO_DENIED')
    sys.addaudithook(deny)
    out={'checks':check_predictions(packet,req['predictions']),
         'independence':{'forbidden_modules_loaded':[m for m in sys.modules if m in {
             'artifact_genesis.proposer','artifact_genesis.binding','davcore.finite','artifact_translation.generator'}],
             'received_target_or_expected_labels':False}}
    print(json.dumps(out,ensure_ascii=False,allow_nan=False))


if __name__=='__main__':main()
