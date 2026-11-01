"""Synthetic source-contract regressions. Not a semantic benchmark or new discovery."""
import json
import os
import sys
from copy import deepcopy
from pathlib import Path
import pytest
sys.path.insert(0, os.environ.get('LM_AUDIT_CODE', str(Path(__file__).resolve().parent)))
from artifact_genesis.source import packet_from_text
from artifact_genesis.contract import RawPacket
from semantic_repair import alignment as a
from semantic_repair.scoped import Claim, compare
from davcore.ast import digest


def case(text, train_lines=1, lang='en'):
    raw = packet_from_text('diagnostic', text, language=lang).model_dump()
    train = RawPacket.model_validate({**raw, 'spans': raw['spans'][:train_lines]})
    validation = RawPacket.model_validate({**raw, 'spans': raw['spans'][train_lines:]})
    frame = a.observe(train)['frames'][0]
    return a.request(frame, a.claim_for_frame(frame), 'local_query', train), a.observe(validation), train, validation


def pair(definition='Here, reply means echo.'):
    return case('Whenever a bell reaches keeper, keeper sends an echo.\n'
                'Whenever a bell reaches keeper, keeper sends a reply.\n'+definition+'\n')


def test_direction_does_not_use_converse():
    req, ev, _, _ = pair('Here, echo means reply.')
    assert a.assess(req, ev)['status'] != 'SUPPORTS_EXACT_CLAIM'


def test_evidence_to_claim_direction_is_usable():
    req, ev, _, _ = pair()
    assert a.assess(req, ev)['status'] == 'SUPPORTS_EXACT_CLAIM'


def test_missing_definition_keeps_hypothesis_not_fact():
    req, ev, _, validation = pair()
    ev = a.observe(validation.model_copy(update={'spans': validation.spans[:1]}))
    assert a.assess(req, ev)['status'] == 'UNRESOLVED'


def test_role_claim_identity_is_not_collapsed():
    p = packet_from_text('actors', 'Whenever a bell reaches keeper, keeper sends an echo.\n'
                         'Whenever a bell reaches sailor, sailor sends an echo.\n')
    frames = a.observe(p)['frames']
    assert len({a.claim_for_frame(f).identity() for f in frames}) == 2


def test_legacy_roleless_digest_is_preserved():
    fields=dict(predicate='P',subject='S',object='O',domain='D',quantifier='ALL',polarity='POSITIVE',
                modality='TEXTUAL_CLAIM',time='GENERIC',stage='S',scope='s',source_hash='a'*64,edition='e',assumptions=())
    claim=Claim(**fields)
    assert claim.identity()==digest(fields)


def test_roleless_claim_not_silently_upgraded_to_exact():
    req,ev,train,_=pair()
    old_fields={k:v for k,v in req['q_s'].items() if k not in ('participant','stimulus_participant','recipient','direction')}
    new_req=a.request(req['source_frame'], Claim.model_validate_json(json.dumps(old_fields)), 'legacy', train)
    assert a.assess(new_req,ev)['status']=='UNRESOLVED'


def test_irrelevant_actor_does_not_veto_direct_evidence():
    req,ev,_,_=case('Whenever a bell reaches keeper, keeper sends an echo.\n'
                     'Whenever a bell reaches keeper, keeper sends an echo.\n'
                     'Whenever a bell reaches sailor, sailor sends an echo.\n')
    result=a.assess(req,ev)
    assert result['status']=='SUPPORTS_EXACT_CLAIM'
    assert len(result['branches'])==2


def test_foreign_actor_alone_not_support():
    req,ev,_,_=case('Whenever a bell reaches keeper, keeper sends an echo.\n'
                     'Whenever a bell reaches sailor, sailor sends an echo.\n')
    assert a.assess(req,ev)['status']=='UNRESOLVED'


def test_shared_location_is_not_a_stimulus_binding():
    req,ev,_,_=case('Ревет ли зверь в лесу,\nНа всякий звук\nСвой отклик\nРодишь ты вдруг.\n'
                    'Ты внемлешь тишине в лесу,\nИ шлешь ответ;\n',4,'ru')
    r=a.assess(req,ev)
    assert not r.get('conditional_support')
    assert not r.get('conditional_alignment_compatible')
    assert 'STIMULUS_ENTAILMENT_NOT_ESTABLISHED' in r['obligations']


def test_two_explicit_actors_are_retained():
    p=packet_from_text('actors', 'Ты внемлешь грохоту громов,\nОн вовсе не шлешь ответ.\n',language='ru')
    f=a.observe(p)['frames'][0]
    assert f['stimulus_actor']=='local_second_person' and f['actor']=='он'


def test_focus_negation_not_discarded_by_search():
    p=packet_from_text('negation', 'Не ты внемлешь грохоту громов,\nИ шлешь ответ;\n',language='ru')
    assert not a.observe(p)['frames']  # unsupported syntax, not a positive input fact


def test_source_compare_is_not_fake_DAV_proof():
    req,ev,_,_=pair()
    r=a.assess(req,ev)
    assert r['status']=='SUPPORTS_EXACT_CLAIM'
    assert not any(x['finite_K_V_and_C_a']['evidence']['status']=='proved' for x in r['branches'])
    assert all(x['finite_K_V_and_C_a']['satisfiable'] is None for x in r['branches'])


def test_unregistered_target_id_is_not_a_target_certificate():
    req,ev,_,_=pair();req=deepcopy(req)
    req['q_t_id']='unregistered';req['translation_binding']['target_query_id']='unregistered'
    r=a.assess(req,ev)
    assert r.get('target_query_verified') is False
    assert r.get('target_entailment_status')=='NOT_RUN'


def test_two_existential_opposites_not_refutation():
    x=Claim(predicate='warm',subject='item',object='yes',domain='items',quantifier='SOME',polarity='POSITIVE',
            modality='TEXTUAL_CLAIM',time='t',stage='s',scope='same',source_hash='a'*64,edition='e')
    y=x.model_copy(update={'polarity':'NEGATIVE'})
    assert compare(x,y,['s1'])['status']!='REFUTES_EXACT_CLAIM'
    assert any((True,False)) and any(not v for v in (True,False))


def test_basis_deletion_invalidates_transport():
    req,ev,_,_=pair();ref=ev['definitions'][0]['source_refs'][0]
    assert a.assess(req,ev,disabled_basis=(ref,))['status']=='UNRESOLVED'


def test_selected_candidate_family_does_not_get_exact_credit():
    req,ev,_,_=pair();f=a.candidates(req,ev)
    f={**f,'candidates':[]}
    assert a.assess(req,ev,f)['status']=='UNRESOLVED'


def test_tampered_frame_rejected():
    req,ev,_,_=pair();ev=deepcopy(ev);ev['frames'][0]['actor']='other'
    with pytest.raises(ValueError,match='OBSERVATION_OR_SOURCE'):
        a.assess(req,ev)


def test_alpha_roles_preserve_admitted_mapping():
    for actor, stimulus in [('keeper','bell'),('watcher','horn')]:
        req,ev,_,_=case(f'Whenever a {stimulus} reaches {actor}, {actor} sends an echo.\n'
                        f'Whenever a {stimulus} reaches {actor}, {actor} sends a reply.\nHere, reply means echo.\n')
        assert a.assess(req,ev)['status']=='SUPPORTS_EXACT_CLAIM'


def test_negative_evidence_uses_contrapositive_direction():
    req,ev,_,_=case('Whenever a bell reaches keeper, keeper sends an echo.\n'
                     'Whenever a bell reaches keeper, keeper does not send a reply.\n'
                     'Here, echo means reply.\n')
    assert a.assess(req,ev)['status']=='REFUTES_EXACT_CLAIM'


def test_negative_evidence_does_not_reverse_wrong_definition():
    req,ev,_,_=case('Whenever a bell reaches keeper, keeper sends an echo.\n'
                     'Whenever a bell reaches keeper, keeper does not send a reply.\n'
                     'Here, reply means echo.\n')
    assert a.assess(req,ev)['status']=='UNRESOLVED'
