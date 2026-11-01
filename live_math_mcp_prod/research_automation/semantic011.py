"""Source proposal/review actions inside the existing durable artifact lifecycle."""
from semantic_repair.inference011 import canonical_packet
from semantic_repair.observe011 import align, symbolic_fallback

STRATEGIES = {'general011/1', 'general011-contrast/1', 'observer012/1', 'observer012-contrast/1', 'observer013/1', 'meaning014/1'}


async def inference_call(controller, case, state, role, packet, context, *, proposals=None, feedback=None):
    provider = controller.semantic_provider
    if provider is None:
        return {'status': 'ERROR', 'reason': 'NO_GENERAL_SEMANTIC_PROPOSER'}
    key = f"artifact-source:{case['id']}:g{state['generation']}:view{state['source_reads']}:{role}"
    canonical, _ = canonical_packet(packet)
    identity = {'source': context.public(), 'packet': canonical, 'role': role,
        'proposals': proposals, 'source_view': feedback, 'provider': provider.fingerprint,
        'coordinator_binding': controller.binding}
    old = controller.service.store.repeated(case['project'], key, identity)
    if old:
        return old['payload']['result']
    attempts = controller.journal.rows(('artifact_worker_attempt',), case['project'], case_id=case['id'])
    same = [r for r in attempts if r['payload']['action_key'] == key]
    budget = case['payload']['problem']['artifact_budget']
    model_calls = [r for r in attempts if r['payload']['mode'].startswith('model_')]
    if len(attempts) >= budget['workers'] or len(model_calls) >= (3 if case['payload']['problem'].get('artifact_interpretation') == 'meaning014' else 8) or len(same) > budget['retries']:
        return {'status': 'ERROR', 'reason': 'SOURCE_MODEL_CALL_BUDGET_EXHAUSTED'}
    controller.journal.append(case['project'], 'artifact_worker_attempt', key + ':attempt:' + str(len(same)),
        {'case_id': case['id'], 'action_key': key, 'attempt': len(same)},
        {'case_id': case['id'], 'generation': state['generation'], 'action_key': key,
            'mode': 'model_' + role, 'attempt': len(same)})
    try:
        result = await provider.infer(role, packet, proposals, feedback)
    except (ValueError, TimeoutError, OSError) as exc:
        result = {'status': 'ERROR', 'reason': type(exc).__name__ + ':' + str(exc)[:1000]}
    controller.journal.append(case['project'], 'artifact_semantic_call', key, identity,
        {'case_id': case['id'], 'generation': state['generation'], 'role': role,
            'source_context': context.public(), 'provider_binding': provider.fingerprint,
            'coordinator_binding': controller.binding, 'result': result})
    return result


async def observe_source(controller, case, state, packet, action, context):
    strategy = action['strategy']
    if strategy not in STRATEGIES:
        raise ValueError('REGISTERED_GENERAL_SOURCE_VIEW_REQUIRED')
    context.require(case['project'])
    if packet['document_sha256'] != context.public()['sha256']:
        raise ValueError('FOREIGN_GENERAL_SOURCE_PACKET')
    key = f"artifact:{case['id']}:g{state['generation']}:read:{state['source_reads']}"
    identity = {'source': context.public(), 'packet': packet, 'strategy': strategy,
        'coordinator_binding': controller.binding}
    existing = controller.service.store.repeated(case['project'], key, identity)
    if existing:
        return existing
    if strategy == 'meaning014/1':
        from .semantic014 import observe
        return await observe(controller, case, state, packet, action, context)
    v012 = strategy.startswith(('observer012', 'observer013'))
    v013 = strategy.startswith('observer013')
    feedback = None if strategy in {'general011/1', 'observer012/1', 'observer013/1'} else {
        'view': 'independent_scope_and_polarity_contrast',
        'unresolved_source_dimensions': ['participant', 'polarity', 'scope', 'projection'],
        'instruction': 'Offer an alternative source reading only where the addressed evidence supports it; do not force a loop or global identity.'}
    proposal = await inference_call(controller, case, state, 'proposer013' if v013 else 'proposer012' if v012 else 'proposer', packet, context, feedback=feedback)
    review = None
    if proposal['status'] == 'OK':
        review = await inference_call(controller, case, state, 'critic013' if v013 else 'critic012' if v012 else 'critic', packet, context,
            proposals=proposal['output'])
    if proposal['status'] == 'OK':
        try:
            if v013:
                from semantic_repair.observe013 import align as align_source
            elif v012:
                from semantic_repair.observe012 import align as align_source
            else:
                align_source = align
            result = align_source(packet, proposal['output'], review['output'] if review and review['status'] == 'OK' else None,
                assurance=getattr(controller.semantic_provider, 'assurance', 'MODEL_BACKEND_ASSURANCE_UNSPECIFIED'))
        except ValueError as exc:
            result = symbolic_fallback(packet)
            result['source_coverage_losses'].append({'reason': 'SOURCE_ALIGNMENT_REQUIRES_REVIEW', 'detail': str(exc)[:1000]})
    else:
        result = symbolic_fallback(packet)
    if proposal['status'] != 'OK' or review is not None and review['status'] != 'OK':
        result['source_coverage_losses'].append({'reason': 'SOURCE_MODEL_UNAVAILABLE_OR_UNDECIDED',
            'proposer_status': proposal['status'], 'proposer_reason': proposal.get('reason'),
            'critic_status': review['status'] if review else None,
            'critic_reason': review.get('reason') if review else None})
    result['source_coverage_losses'] += [{'reason': 'MODEL_OUTPUT_FRAGMENT_NOT_ADMITTED', **loss}
        for loss in proposal.get('decoding_losses', [])]
    result.update(observer=strategy, model_provider_binding=getattr(controller.semantic_provider, 'fingerprint', None),
        model_calls_contain_only_source=True, source_claim_verified=False)
    return controller.journal.append(case['project'], 'artifact_checkpoint', key, identity,
        {'case_id': case['id'], 'generation': state['generation'], 'action': 'observe',
            'result': result, 'source_context': context.public(), 'coordinator_binding': controller.binding})


def attention_actions(observations, windows, state):
    """One distinct source re-reading per window; never repeat until a label fits."""
    obligations = []
    actions = []
    by_window = {o['source_packet']['id']: o for o in observations if o['observer'] in STRATEGIES}
    for index, window in enumerate(windows[:state['next_window']]):
        current = by_window.get(window['id'])
        if current is None or current['observer'] in {'observer013/1','meaning014/1'} or current['observer'] in {'general011-contrast/1', 'observer012-contrast/1', 'observer013/1'}:
            continue
        losses = current.get('general_source_loss_ledger', [])
        unsettled = bool(losses or current.get('unparsed_refs'))
        if not unsettled:
            continue
        kind = 'POLARITY_COLLISION' if any('POLARITY' in str(loss.get('reason', '')) or loss.get('status') == 'CONFLICT' for loss in losses) else 'UNKNOWN_LINK'
        obligations.append({'kind': kind, 'window': index, 'source_only': True})
        actions.append({'id': 'source-contrast:' + str(index), 'window': index,
            'strategy': 'observer012-contrast/1' if current['observer'].startswith('observer012') else 'general011-contrast/1', 'covers': [kind], 'cost': 1})
    return obligations, actions
