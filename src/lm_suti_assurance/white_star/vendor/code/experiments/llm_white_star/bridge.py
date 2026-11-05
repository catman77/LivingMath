"""A transparent, bounded text-to-CAD input/output adapter.

The solver is the existing native WhiteStar/CAD/UDAV implementation. This file
does not score candidate projections, generate prose, or optimize a TSP.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from math import gcd
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
WS = HERE.parent / "white_star"
if str(WS) not in sys.path:
    sys.path.insert(0, str(WS))
from fast_source import FastWhiteStarSource


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def validate(data):
    if data.get("schema") != "llm-white-star-concepts/1":
        raise ValueError("unsupported concept schema")
    raw = data["source"]["text"].encode()
    if hashlib.sha256(raw).hexdigest() != data["source"]["sha256"]:
        raise ValueError("source SHA256 mismatch")
    concepts = data["concepts"]
    if not 3 <= len(concepts) <= 64:
        raise ValueError("the native atlas supports 3..64 concepts in this adapter")
    ids, vectors = set(), set()
    for concept in concepts:
        key = concept["id"]
        if not isinstance(key, str) or not key or key in ids:
            raise ValueError("concept IDs must be unique nonempty strings")
        ids.add(key)
        vector = concept["coordinates"]
        if len(vector) != 2 or any(type(v) is not int or abs(v) > 1_000_000 for v in vector):
            raise ValueError("two bounded integer coordinates required")
        vector = tuple(vector)
        if vector == (0, 0) or vector in vectors:
            raise ValueError("coordinates must be nonzero and distinct")
        vectors.add(vector)
        if not concept["evidence"]:
            raise ValueError("every concept requires source evidence")
        for citation in concept["evidence"]:
            lo, hi = citation["byte_start"], citation["byte_end"]
            if type(lo) is not int or type(hi) is not int or not 0 <= lo < hi <= len(raw):
                raise ValueError("invalid source address")
            if raw[lo:hi] != citation["quote"].encode():
                raise ValueError("source citation mismatch")
            if raw[:lo].count(b"\n") + 1 != citation["line"]:
                raise ValueError("source line mismatch")
    for relation in data["source_relations"]:
        if not set(relation["concepts"]) <= ids:
            raise ValueError("source relation names an absent concept")


def compile_atlas(data):
    """All nonsingular ordered pairs of concept rows, not interpretations.

    Source address, then coordinate value, defines order. ID spelling and JSON
    list order cannot influence selection. A determinant-zero pair cannot form
    a reversible coordinate chart and is recorded as omitted.
    """
    validate(data)
    concepts = sorted(data["concepts"], key=lambda c: (
        min(e["byte_start"] for e in c["evidence"]), tuple(c["coordinates"])))
    charts, omitted = [], []
    for left in concepts:
        for right in concepts:
            if left is right:
                continue
            a, b = left["coordinates"]
            c, d = right["coordinates"]
            determinant = a * d - b * c
            pair = [left["id"], right["id"]]
            if determinant == 0:
                omitted.append(pair)
            else:
                charts.append(dict(view=len(charts), pair=pair, matrix=[a, b, c, d],
                                   determinant=determinant,
                                   orthogonal_rows=(a * c + b * d == 0)))
    if len(charts) < data["protocol"]["candidates_per_step"]:
        raise ValueError("not enough independent CAD charts")
    return dict(schema="llm-white-star-atlas/1", charts=charts,
                omitted_collinear_pairs=omitted,
                ordered_pair_count=len(concepts) * (len(concepts) - 1),
                semantics="rows name concepts; matrices act on division witnesses, not on truth values")


def readout(record, atlas):
    chart = atlas["charts"][record.view]
    x, y = record.coordinates
    normalizer = gcd(abs(x), abs(y)) or 1
    relation = "ALIGN" if x * y > 0 else "TENSION" if x * y < 0 else "UNRESOLVED"
    dominance = "BALANCED" if abs(x) == abs(y) else chart["pair"][0 if abs(x) > abs(y) else 1]
    return dict(step=record.step, view=record.view, concepts=chart["pair"],
                proposed_relation=relation, signed_weights=[x // normalizer, y // normalizer],
                dominant=dominance,
                status="CREATIVE_RELATION_PROPOSAL_NOT_SOURCE_ENTAILMENT")


def run_search(data):
    atlas = compile_atlas(data)
    protocol = data["protocol"]
    count = protocol["steps"]
    size = protocol["frame_size"]
    if type(count) is not int or not 1 <= count <= 100_000:
        raise ValueError("steps must be an integer in 1..100000")
    if type(size) is not int or not 1 <= size <= count:
        raise ValueError("frame size must be a positive integer within the budget")
    with FastWhiteStarSource(seed=protocol["seed"], k=protocol["candidates_per_step"],
                             charts=[c["matrix"] for c in atlas["charts"]]) as source:
        batch = source.read(count, audit=True)
        records = batch.observations()
        stats = source.snapshot()
    observations = [asdict(record) for record in records]
    proposals = [readout(record, atlas) for record in records if record.direction_defined]
    frames = []
    for offset in range(0, len(proposals) - size + 1, size):
        links = proposals[offset:offset + size]
        # A frame is simply consecutive proposals, not an independently ranked
        # candidate interpretation. No semantic optimizer is hidden here.
        ids = list(dict.fromkeys(c for link in links for c in link["concepts"]))
        frames.append(dict(id=f"F{len(frames) + 1:02}", steps=[p["step"] for p in links],
                           concepts=ids, links=links))
    selected_frames = frames[:protocol["decode_first_frames"]]
    summary = dict(
        **stats, source_concepts=len(data["concepts"]),
        charts_nonorthogonal=sum(not c["orthogonal_rows"] for c in atlas["charts"]),
        omitted_collinear_pairs=len(atlas["omitted_collinear_pairs"]),
        per_witness_atlas_fraction=stats["projections"] / (count * len(atlas["charts"])),
        fraction_denominator="steps * available charts; NOT fraction of interpretations",
        frames=len(frames), decoded_frames=len(selected_frames),
        concepts_in_all_frames=len({c for f in frames for c in f["concepts"]}),
        concepts_in_decoded_frames=len({c for f in selected_frames for c in f["concepts"]}),
        relation_signatures=len({(p["proposed_relation"], *p["concepts"]) for p in proposals}),
        full_interpretations_searched=0, literary_quality_scored=False,
    )
    return dict(input_sha256=digest(data), atlas=atlas, observations=observations,
                frames=frames, selected_frames=selected_frames, summary=summary)


def decoder_packet(data, result):
    return dict(
        schema="llm-white-star-decoder/1", source=data["source"], axes=data["axes"],
        concepts=data["concepts"], source_relations=data["source_relations"],
        uncertainties=data["uncertainties"], frames=result["selected_frames"],
        instruction=(
            "Для каждого из шести кадров напиши самостоятельный короткий образ/прочтение. "
            "Используй все названные в кадре понятия и отрази его три отношения. "
            "ALIGN предлагает совместный мотив, TENSION — напряжение, UNRESOLVED оставляет связь открытой. "
            "Это условие интерфейса, а не вывод о значении слов. Величина |веса| задаёт внимание, "
            "не истинность; знак не разрешает отрицать исходную строку. "
            "Добавляй свободные ассоциации, но отдельно перечисли внесённые метафоры и предположения. "
            "Не представляй утверждения лирического голоса как доказанные законы мира. "
            "Не утверждай, что Удав нашёл лучшую интерпретацию или написал текст. "
            "Назови использованные концепты, предложенные связи и то, что не смог связать. "
            "Не выбирай удобные кадры и не меняй вход после чтения результатов."
        ),
    )
