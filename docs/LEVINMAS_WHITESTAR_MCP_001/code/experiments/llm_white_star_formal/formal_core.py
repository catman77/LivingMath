"""Exact, post-search audit of experiment 001; never a candidate selector.

This module uses rational arithmetic to characterize a fixed readout. It does
not define semantic truth, a new search objective, or a replacement for UDAV.
"""
from __future__ import annotations

from collections import Counter
from fractions import Fraction
from itertools import combinations
import hashlib
import json
from math import gcd
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / "llm_white_star"
WS = HERE.parent / "white_star"
CLAIM_QUOTES = ["Всё будет так.", "Исхода нет.", "Умрешь — начнешь опять сначала,",
                "И повторится всё, как встарь:"]
sys.path.insert(0, str(BASE))
from bridge import compile_atlas, validate


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def load_case():
    data = json.loads((BASE / "input/concepts.json").read_text())
    results = BASE / "results"
    trace = [json.loads(line) for line in (results / "trace.jsonl").read_text().splitlines()]
    frames = json.loads((results / "frames.json").read_text())
    prose = json.loads((results / "decoder_response.json").read_text())
    return data, trace, frames, prose


def qualitative(pair, x, y):
    """Forget row order and absolute scale, retaining concept identities.

    This is a declared diagnostic quotient. The original ordered trace is not
    modified, and we do not assume that prose is insensitive to word order.
    """
    if len(set(pair)) != 2 or (x == 0 and y == 0):
        raise ValueError("two different concepts and a nonzero projection required")
    relation = "ALIGN" if x * y > 0 else "TENSION" if x * y < 0 else "UNRESOLVED"
    dominant = pair[0] if abs(x) > abs(y) else pair[1] if abs(y) > abs(x) else "BALANCED"
    return (*sorted(pair), relation, dominant)


def projective(pair, x, y):
    """Exact relative weights, modulo common nonzero scale and row order."""
    if not (x or y):
        raise ValueError("the zero witness has no projective readout")
    if pair[0] > pair[1]:
        pair, x, y = pair[::-1], y, x
    x, y = Fraction(x), Fraction(y)
    # Normalize the first nonzero component to +1; this is exact over Q.
    anchor = x if x else y
    return tuple(pair), str(x / anchor), str(y / anchor)


def pair_cells(left, right, u, v):
    """Complete partition of t=a/(a+b) in [0,1] for a fixed pair.

    The only possible changes are roots of L, R, L-R, L+R. Each open
    interval and boundary point is assigned an explicit integer witness.
    Completeness follows from constant signs of affine functions between
    roots; it is not inferred from a dense numerical grid.
    """
    a, b = u
    c, d = v
    if a * d == b * c:
        raise ValueError("singular pair is not in experiment 001's atlas")
    affine = {"left_zero": (b, a - b), "right_zero": (d, c - d),
              "same_value": (b - d, a - b - c + d),
              "opposite_value": (b + d, a - b + c - d)}
    cuts = {Fraction(0), Fraction(1)}
    root_records = []
    for event, (constant, slope) in affine.items():
        if slope:
            root = -Fraction(constant, slope)
            if 0 <= root <= 1:
                cuts.add(root)
                root_records.append(dict(event=event, root=str(root)))
        elif constant == 0:
            root_records.append(dict(event=event, root="IDENTICALLY_ZERO"))
    ordered = sorted(cuts)
    pieces = [("POINT", t, t, t) for t in ordered]
    pieces += [("OPEN_INTERVAL", l, r, (l + r) / 2) for l, r in zip(ordered, ordered[1:])]
    cells = []
    witnesses = {}
    for kind, lo, hi, t in pieces:
        wa, wb = t.numerator, t.denominator - t.numerator
        x, y = a * wa + b * wb, c * wa + d * wb
        state = qualitative([left, right], x, y)
        witness = dict(t=str(t), witness=[wa, wb], coordinates=[x, y])
        cells.append(dict(kind=kind, lo=str(lo), hi=str(hi), state=state, **witness))
        witnesses.setdefault(state, witness)
    return dict(concepts=[left, right], vectors=[u, v], determinant=a * d - b * c,
                roots=root_records, cells=cells,
                states=[dict(state=k, **w) for k, w in sorted(witnesses.items())],
                relation_types=sorted({k[2] for k in witnesses}))


def reachability(data):
    atlas = compile_atlas(data)
    vectors = {c["id"]: c["coordinates"] for c in data["concepts"]}
    pairs = sorted({tuple(sorted(c["pair"])) for c in atlas["charts"]})
    audits = [pair_cells(i, j, vectors[i], vectors[j]) for i, j in pairs]
    states = {tuple(r["state"]) for a in audits for r in a["states"]}
    fixed = [a for a in audits if len(a["relation_types"]) == 1]
    return dict(
        schema="white-star-qualitative-reachability/1", pairs=audits,
        omitted_collinear_pairs=sorted({tuple(sorted(p)) for p in atlas["omitted_collinear_pairs"]}),
        summary=dict(ordered_maps=len(atlas["charts"]), unordered_pairs=len(pairs),
                     qualitative_states=len(states), fixed_relation_pairs=len(fixed),
                     fixed_align=sum(a["relation_types"] == ["ALIGN"] for a in fixed),
                     fixed_tension=sum(a["relation_types"] == ["TENSION"] for a in fixed),
                     changeable_relation_pairs=len(pairs) - len(fixed),
                     domain="all nonzero witnesses (a,b) in N^2; t=a/(a+b) rational in [0,1]",
                     result_status="EXACT_FOR_FIXED_TWO_COORDINATE_READOUT"))


def verify_reference_trace(data, trace):
    """Replay the unchanged Python algorithm with the frozen custom atlas."""
    import cad
    import source
    atlas = compile_atlas(data)
    matrices = tuple(tuple(c["matrix"]) for c in atlas["charts"])
    # This is the exact frozen 180-chart case. The general native atlas has a
    # coprime-stride extension, so do not silently apply this reference audit
    # to atlases where the original stride 11 is not coprime.
    if gcd(11, len(matrices)) != 1:
        raise ValueError("this reference replay requires atlas size coprime to 11")
    old_cad, old_source = cad.CHARTS, source.CHARTS
    try:
        cad.CHARTS = source.CHARTS = matrices
        controller = source.WhiteStarSource(seed=data["protocol"]["seed"],
                                             k=data["protocol"]["candidates_per_step"])
        expected = [controller.next().to_dict() for _ in range(data["protocol"]["steps"])]
    finally:
        cad.CHARTS, source.CHARTS = old_cad, old_source
    if encode(expected) != encode(trace):
        raise ValueError("trace does not equal the frozen reference computation")
    return True


def audit_observed(data, trace, frames, reachable):
    atlas = compile_atlas(data)
    possible = {tuple(s["state"]) for pair in reachable["pairs"] for s in pair["states"]}
    observed, numeric, duplicates, pair_set, edges = set(), set(), [], set(), []
    witnessed = {}
    for record in trace:
        if not any(record["witness"]):
            continue
        pair = atlas["charts"][record["view"]]["pair"]
        state = qualitative(pair, *record["coordinates"])
        assert state in possible
        sig = tuple(record["signature"])
        if state in observed and sig not in numeric:
            duplicates.append(dict(step=record["step"], previous_step=witnessed[state],
                                   state=state, new_arithmetic_signature=sig,
                                   previous_arithmetic_signature=trace[witnessed[state]]["signature"]))
        witnessed.setdefault(state, record["step"])
        observed.add(state)
        numeric.add(sig)
        pair_set.add(tuple(sorted(pair)))
        edges.append(dict(step=record["step"], state=state,
                          projective_state=projective(pair, *record["coordinates"])))
    by_step = {e["step"]: tuple(e["state"]) for e in edges}
    frame_signatures = []
    for frame in frames:
        sequence = tuple(by_step[t] for t in frame["steps"])
        frame_signatures.append(dict(id=frame["id"], steps=frame["steps"], sequence=sequence,
                                     unordered_multiset=sorted(sequence),
                                     distinct_concept_pairs=len({s[:2] for s in sequence})))
    first = frame_signatures[:data["protocol"]["decode_first_frames"]]
    return dict(
        edges=edges, frames=frame_signatures,
        arithmetic_new_but_qualitatively_repeated=duplicates,
        summary=dict(
            nonzero_observations=len(edges), unique_qualitative_states=len(observed),
            reachable_qualitative_states=len(possible),
            reachable_fraction=len(observed) / len(possible),
            unique_observed_unordered_pairs=len(pair_set),
            unique_projective_states=len({encode(e["projective_state"]) for e in edges}),
            all_frame_sequences_distinct=len({encode(f["sequence"]) for f in frame_signatures}) == len(frames),
            first_six_motifs_distinct=len({encode(f["unordered_multiset"]) for f in first}) == len(first),
            first_six_unique_pairs=len({s[:2] for f in first for s in f["sequence"]}),
            fresh_arithmetic_repeated_qualitative=len(duplicates),
            meaning_of_fraction="coverage of a declared qualitative edge readout, not literary meanings"))


def locate(text, quote):
    """A unique UTF-8 excerpt address, including multi-byte Cyrillic."""
    if not quote or text.count(quote) != 1:
        raise ValueError("excerpt must occur exactly once")
    pos = text.index(quote)
    lo = len(text[:pos].encode())
    return dict(byte_start=lo, byte_end=lo + len(quote.encode()), quote=quote)


def check_excerpt(text, address):
    raw = text.encode()
    lo, hi = address["byte_start"], address["byte_end"]
    if type(lo) is not int or type(hi) is not int or not 0 <= lo < hi <= len(raw):
        raise ValueError("bad excerpt address")
    if raw[lo:hi] != address["quote"].encode():
        raise ValueError("excerpt mismatch")


def check_certificate(data, trace, frames, certificate, *, replay=True):
    """Check arithmetic/provenance contracts, never certify prose semantics."""
    validate(data)
    if replay:
        verify_reference_trace(data, trace)
    if certificate["schema"] != "white-star-interpretation-certificate/1":
        raise ValueError("unknown certificate schema")
    if certificate["semantic_fidelity"] != "LLM_ANNOTATED_NOT_INDEPENDENTLY_VERIFIED":
        raise ValueError("cannot promote a prose annotation to a proved semantic judgement")
    if certificate["source_sha256"] != data["source"]["sha256"]:
        raise ValueError("wrong source")
    atlas = compile_atlas(data)
    concepts = {c["id"]: c for c in data["concepts"]}
    # Reconstruct frame assembly, so the supplied frame file cannot silently
    # change the precommitted selection or omit an inconvenient observation.
    proposals = []
    for record in trace:
        if not any(record["witness"]):
            continue
        pair = atlas["charts"][record["view"]]["pair"]
        x, y = record["coordinates"]
        state = qualitative(pair, x, y)
        normalizer = gcd(abs(x), abs(y)) or 1
        proposals.append(dict(step=record["step"], view=record["view"], concepts=pair,
                              proposed_relation=state[2], signed_weights=[x // normalizer, y // normalizer],
                              dominant=state[3], status="CREATIVE_RELATION_PROPOSAL_NOT_SOURCE_ENTAILMENT"))
    expected_frames = []
    size = data["protocol"]["frame_size"]
    for offset in range(0, len(proposals) - size + 1, size):
        links = proposals[offset:offset + size]
        expected_frames.append(dict(id=f"F{len(expected_frames)+1:02}", steps=[l["step"] for l in links],
                                    concepts=list(dict.fromkeys(c for l in links for c in l["concepts"])),
                                    links=links))
    if encode(frames) != encode(expected_frames):
        raise ValueError("frames differ from the frozen consecutive assembly rule")
    if [a["source_excerpt"]["quote"] for a in certificate["source_assertions"]] != CLAIM_QUOTES:
        raise ValueError("source assertion register differs from the frozen Blok annotation")
    for assertion in certificate["source_assertions"]:
        check_excerpt(data["source"]["text"], assertion["source_excerpt"])
        if assertion["epistemic_type"] != "ATTRIBUTED_TO_LYRICAL_VOICE":
            raise ValueError("speaker content cannot be promoted to a world fact")
        if assertion["world_truth"] != "UNDETERMINED":
            raise ValueError("source statement alone cannot establish its world truth")
        if assertion["classification_status"] != "SOURCE_MODEL_ANNOTATION":
            raise ValueError("linguistic scope annotation is not mechanically established")
    selected = frames[:data["protocol"]["decode_first_frames"]]
    readings = certificate["readings"]
    if [f["id"] for f in selected] != [r["frame_id"] for r in readings]:
        raise ValueError("missing, reordered or added frame")
    for frame, reading in zip(selected, readings):
        if reading["text_sha256"] != hashlib.sha256(reading["text"].encode()).hexdigest():
            raise ValueError("prose hash mismatch")
        bindings = reading["bindings"]
        if [b["step"] for b in bindings] != frame["steps"]:
            raise ValueError("every selected edge must have one ordered binding")
        for binding in bindings:
            record = trace[binding["step"]]
            pair = atlas["charts"][record["view"]]["pair"]
            expected = qualitative(pair, *record["coordinates"])
            if tuple(binding["state"]) != expected:
                raise ValueError("binding misstates the selected relation or dominance")
            if binding["status"] != "CREATIVE_RELATION_PROPOSAL":
                raise ValueError("CAD relation cannot be promoted to source entailment")
            if set(binding["source_anchors"]) != set(pair):
                raise ValueError("binding must anchor both and only both source concepts")
            for key, addresses in binding["source_anchors"].items():
                if addresses != concepts[key]["evidence"]:
                    raise ValueError("binding cites different source evidence")
            check_excerpt(reading["text"], binding["prose_excerpt"])
            if binding["interpretation_status"] != "LLM_SELF_ANNOTATION":
                raise ValueError("unverified interpretation annotation status")
        if reading["status"] != "CREATIVE_READING_NOT_SOURCE_FACT":
            raise ValueError("interpretation cannot be promoted to a source fact")
        for addition in reading["additions"]:
            if addition["status"] != "LLM_CREATIVE_EXTENSION":
                raise ValueError("added metaphor cannot be promoted to source fact")
    return dict(arithmetic_trace="PASS" if replay else "NOT_REPLAYED_THIS_CALL",
                source_addresses="PASS", frame_and_relation_bindings="PASS",
                prose_excerpt_addresses="PASS", type_separation="PASS",
                semantic_fidelity="UNASSESSED_BY_CHECKER", aesthetic_quality="UNASSESSED_BY_CHECKER",
                readings=len(readings), bindings=sum(len(r["bindings"]) for r in readings))
