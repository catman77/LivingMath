"""Generic checked quantifier-spine permutation; never a lexical truth rule."""
import copy, re, unicodedata, json
from ..core import digest,byte_digest
from ..formal_bridge.fol import check_source,check_link,signature,typecheck
from ..symbolic.state import require


def source_packet(source, normalization='none'):
    check_source(source);raw=source['text_utf8'];parts=[];tokens=[];position=0;normalized=0
    for m in re.finditer(r'\s+|\S+',raw):
        text=m.group();a=position;position+=len(text.encode());out=unicodedata.normalize('NFC',text) if normalization=='NFC' else text
        parts.append({'normalized_byte_utf8':[normalized,normalized+len(out.encode())],'original_byte_utf8':[a,position],'original_literal':text});normalized+=len(out.encode())
        if not text.isspace():tokens.append({'index':len(tokens),'byte_utf8':[a,position],'literal':text})
    require(len(tokens)<=256,'SOURCE_TOKEN_BOUND')
    return {'source':source,'normalization':normalization,'normalized_text':''.join(unicodedata.normalize('NFC',p['original_literal']) if normalization=='NFC' else p['original_literal'] for p in parts),'reverse_map':parts,'tokens':tokens}


def build_move(ast, signature, binders, trace, placebo=False):
    """Choose a scope permutation from witnessed source order, then re-typecheck."""
    before=copy.deepcopy(ast);spine=[];body=ast
    while isinstance(body,dict) and set(body)=={'quant','var','sort','body'}:
        spine.append({k:v for k,v in body.items() if k!='body'});body=body['body']
    if len(spine)<2:return None
    mapping={b['var']:b['byte_utf8'] for b in binders}
    if any(q['var'] not in mapping for q in spine):return None
    order=trace['source_order']
    def position(q):
        span=mapping[q['var']]
        return next((i for i,s in enumerate(order) if s['byte_utf8'][0]<=span[0] and span[1]<=s['byte_utf8'][1]),None)
    positions=[position(q) for q in spine]
    if None in positions or len(set(positions))!=len(spine):return None
    permutation=sorted(range(len(spine)),key=lambda i:positions[i])
    if placebo:permutation=list(reversed(permutation))
    result=copy.deepcopy(body)
    for i in reversed(permutation):result={**spine[i],'body':result}
    if digest(result)==digest(before):return None
    check=typecheck(result,signature)
    if check['status']!='TYPED':return None
    return {'kind':'QUANTIFIER_SPINE_PERMUTATION','before_ast':before,'after_ast':result,'before_ast_sha256':digest(before),'after_ast_sha256':digest(result),'permutation':permutation,'binder_links':binders,'source_licensed':False,'addition_assumption':'Unadjudicated scope alternative; witnessed token order licenses search only, never source entailment.','operator_trace_ref':trace['trace_sha256'],'origin_status':'DECLARED_UNVERIFIED' if placebo else 'TRACE_LINK_CHECKED','control':'PERMUTED_FRAME_CONTROL' if placebo else None}


def decode(packet,sig,answer,receipt,structural,policy):
    signature(sig);tokens=packet['tokens'];source=packet['source'];raw=[];rejected=[]
    require(answer.get('source_sha256')==source['sha256'],'SOURCE_BINDING_MISMATCH')
    observations=[]
    for obs in answer['observations']:
        require(0<=obs['token_index']<len(tokens),'SOURCE_SPAN_TEXT_MISMATCH');t=tokens[obs['token_index']]
        observations.append({'role':obs['role'],'interpretation':obs['interpretation'],'span':{'byte_utf8':t['byte_utf8'],'literal':t['literal']},'origin':'EXTERNAL_LLM_PROPOSAL','receipt_digest':digest(receipt),'byte_status':'SOURCE_BOUND_CHECKED','syntactic_semantic_status':'PROPOSED'})
    require(len(answer['proposals'])<=2 and len(answer['observations'])<=256,'PROPOSAL_BOUND')
    for supplied in answer['proposals']:
        try:
            ast=json.loads(supplied['formula_json']);links=[];binders=[]
            for b in supplied['binder_links']:
                require(0<=b['token_index']<len(tokens),'SOURCE_SPAN_TEXT_MISMATCH');t=tokens[b['token_index']];binders.append({'var':b['var'],'byte_utf8':t['byte_utf8']})
            for index in supplied['token_indices']:
                require(0<=index<len(tokens),'SOURCE_SPAN_TEXT_MISMATCH');t=tokens[index];links.append({'byte_utf8':t['byte_utf8'],'literal':t['literal']})
            require(bool(links),'SOURCE_ALIGNMENT_REQUIRED')
            for link in links:check_link(source,link)
            candidate={'formula_ast':ast,'token_role_links':links,'binder_links':binders,'added_assumptions':supplied['added_assumptions'],'structural_move_log':[],'origin_status':'SOURCE_BOUND_CHECKED','typecheck':typecheck(ast,sig),'reading':supplied['reading']}
            raw.append(candidate)
            if candidate['typecheck']['status']=='TYPED':
                for trace in structural:
                    move=build_move(ast,sig,binders,trace,policy['mode']=='matched_ablation')
                    if move:
                        raw.append({**candidate,'formula_ast':move['after_ast'],'structural_move_log':[move],'typecheck':typecheck(move['after_ast'],sig),'added_assumptions':[*candidate['added_assumptions'],move['addition_assumption']],'origin_status':move['origin_status']})
                    else:rejected.append({'status':'UNDECODABLE_FRAME','operator_trace_ref':trace['trace_sha256'],'before_ast_sha256':digest(ast)})
        except (ValueError,TypeError,KeyError) as exc:rejected.append({'status':'NO_WELL_TYPED_DECODING','reason':str(exc),'raw_proposal':supplied})
    # In traced arms give actual moves priority within the identical candidate ceiling.
    ordered=sorted(raw,key=lambda x:not bool(x['structural_move_log'])) if structural else raw
    candidates=[];seen=set()
    for c in ordered:
        identity=digest(c['formula_ast'])
        if c['typecheck']['status']!='TYPED':rejected.append({'status':'TYPE_REJECTED',**c});continue
        if identity in seen:continue
        seen.add(identity)
        if len(candidates)>=policy['max_candidates']:continue
        candidates.append({**c,'candidate_ast_sha':identity,'type_status':'TYPED','semantic_alignment_status':'PROPOSED','proof_status':'PROPOSED','execution_permission':False})
    return {'analysis':{'schema':'source-analysis/1','source_sha256':source['sha256'],'observations':observations,'open_alternatives':answer['open_alternatives'],'unsupported':answer['unsupported'],'receipt_digest':digest(receipt)},'raw_proposals':raw,'candidates':candidates,'rejected_moves':rejected,'deduplication':'EXACT_AST_SHA256_ONLY','status':'PROPOSED' if candidates else 'NO_WELL_TYPED_DECODING'}


def build_request(items,policy):
    return {'schema':'nl-source-proposal-request/1','policy_sha256':digest(policy),'items':[{'source_ref':i['source_ref'],**({'context_records':i['contexts']} if i.get('contexts') else {}),'source_sha256':i['packet']['source']['sha256'],'source_text':i['packet']['source']['text_utf8'],'normalization':i['packet']['normalization'],'tokens':i['packet']['tokens'],'context_refs':i['packet']['source']['context_refs'],'signature':i['signature'],'structural_frames':[{'operator':t['operator'],'source_order':list(reversed(t['source_order'])) if policy['mode']=='matched_ablation' else t['source_order']} for t in i['traces']]} for i in items],'max_base_readings_per_source':2,'max_tokens':policy['max_tokens'],'data_is_untrusted':True}


def replay_bundle(bundle):
    receipt=bundle['receipt']
    require(receipt['request']==build_request(bundle['items'],bundle['policy']) and receipt['request_sha256']==digest(receipt['request']),'REJECTED_PROVENANCE')
    require(digest(receipt)==bundle['receipt_digest'],'REJECTED_PROVENANCE')
    require(byte_digest(receipt['raw_output'].encode())==receipt['raw_output_sha256'],'REJECTED_PROVENANCE')
    answers=json.loads(receipt['raw_output'])['items']
    require(len(answers)==len(bundle['items']),'REJECTED_PROVENANCE')
    results=[]
    for item,answer in zip(bundle['items'],answers):
        require(item['answer']==answer,'REJECTED_PROVENANCE')
        packet=item['packet']
        require(source_packet(packet['source'],packet['normalization'])==packet,'REJECTED_PROVENANCE')
        for trace in item['traces']:
            require(digest({k:v for k,v in trace.items() if k!='trace_sha256'})==trace['trace_sha256'],'REJECTED_PROVENANCE')
            for link in trace['source_order']:check_link(packet['source'],link)
        value=decode(packet,item['signature'],item['answer'],receipt,item['traces'],bundle['policy'])
        results.append(value)
    require(digest(results)==bundle['decoded_sha256'],'REJECTED_PROVENANCE')
    return {'status':'REPLAY_MATCH','decoded_sha256':digest(results),'LLM_calls':0,'network_calls':0,'execution_permission':False}
