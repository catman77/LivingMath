"""Retrospective, explicit LLM annotations of the six existing texts.

These excerpts are not an independent semantic audit. Their addresses, types
and correspondence to the computed edges can be mechanically verified.
"""
from formal_core import qualitative, locate, compile_atlas, CLAIM_QUOTES
import hashlib

EXCERPTS = {
    "F01": [
        "У смерти здесь больше определённости, чем у тусклого света: она хотя бы умеет оборвать фразу.",
        "Ночь обступает аптеку, как болезнь, для которой ещё не придумали лекарства.",
        "Но ледяная рябь не соглашается быть «как встарь»: каждый её излом заново портит старую фотографию.",
    ],
    "F02": [
        "По улице течёт ходьба, по каналу — вода.",
        "По улице течёт ходьба, по каналу — вода.",
        "Смерть вынимает из этой схемы одного человека; повторению остаётся пустое место, которое оно заполняет следующим.",
    ],
    "F03": [
        "тусклый свет ничего не обещает о возможности исцеления.",
        "Фонарь подтверждает, что аптека дежурит;",
        "Можно снова и снова приходить к этой двери, но неподвижный фонарь не ведёт счёта возвращениям.",
    ],
    "F04": [
        "Аптека кажется складом консервантов для прошлого.",
        "Ночь лежит в канале тёмным лаком;",
        "улица и тусклый свет вместе удерживают старую сцену.",
    ],
    "F05": [
        "Аптека распускается в ледяной ряби, будто сама растворяется в лекарстве.",
        "Фонарь тем временем штампует удостоверения: «Всё будет так».",
        "Но ночь шире освещённого участка и не обязана соблюдать этот приговор.",
    ],
    "F06": [
        "Фонарь служит ночи: отмечает её границы, не рассеивая её целиком.",
        "Аптека предлагает остановиться у спасительной двери, улица уводит дальше.",
        "«Начнёшь опять сначала» здесь можно услышать как перевес начала над повтором: знакомые предметы ещё на месте, но взгляд уже собирает их в другом порядке.",
    ],
}


def make_certificate(data, trace, frames, prose):
    atlas = compile_atlas(data)
    concepts = {c["id"]: c for c in data["concepts"]}
    readings = []
    selected = frames[:data["protocol"]["decode_first_frames"]]
    for frame, text in zip(selected, prose["readings"]):
        assert frame["id"] == text["frame_id"]
        bindings = []
        for step, quote, annotation in zip(frame["steps"], EXCERPTS[frame["id"]], text["links"]):
            observation = trace[step]
            pair = atlas["charts"][observation["view"]]["pair"]
            bindings.append(dict(
                step=step, state=qualitative(pair, *observation["coordinates"]),
                status="CREATIVE_RELATION_PROPOSAL",
                source_anchors={key: concepts[key]["evidence"] for key in pair},
                prose_excerpt=locate(text["text"], quote),
                interpretation_status="LLM_SELF_ANNOTATION",
                explanation=annotation["rendered_as"],
                semantic_judge="same assistant; no independent judge",
            ))
        readings.append(dict(frame_id=frame["id"], title=text["title"], text=text["text"],
                             text_sha256=hashlib.sha256(text["text"].encode()).hexdigest(),
                             status="CREATIVE_READING_NOT_SOURCE_FACT", bindings=bindings,
                             additions=[dict(description=a, status="LLM_CREATIVE_EXTENSION")
                                        for a in text["introduced"]]))
    return dict(schema="white-star-interpretation-certificate/1",
                source_sha256=data["source"]["sha256"],
                semantic_fidelity="LLM_ANNOTATED_NOT_INDEPENDENTLY_VERIFIED",
                timing="retrospective formalization of experiment 001; no new prose generated",
                source_assertions=[dict(
                    source_excerpt=locate(data["source"]["text"], quote),
                    epistemic_type="ATTRIBUTED_TO_LYRICAL_VOICE", world_truth="UNDETERMINED",
                    classification_status="SOURCE_MODEL_ANNOTATION") for quote in CLAIM_QUOTES],
                readings=readings)
