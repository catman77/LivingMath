"""Frozen ingress into the ACTUAL existing source/finite assurance Bridge facade.

No extraction, no native SUTI claim, no invented semantic relation. Added task
assumptions are explicit; declared concepts/relations remain hypotheses.
"""

from .. import core
from ..core import canonical, digest

POLICY = {
    "schema": "lm-suti.assurance.publication-policy/0.1",
    "audiences": ["private"],
    "allow_source_bytes": True,
    "reason": "Owner-supplied frozen input, private task audience only",
}
BACKEND = "SemanticBridge001/source-assurance-frozen-ingress/1"


def run(base, project, common, common_ref, slots):
    sid = "frozen-semantic:" + digest(common)
    source = core.contracts.SourceSnapshot.create(
        sid,
        canonical(common),
        "Owner supplied frozen encoding; rights declaration: "
        + common["source"]["rights"],
        kind="qa",
        can_embed=common["source"]["rights"]
        in (
            "PUBLIC_DOMAIN",
            "ORIGINAL_TEST_FIXTURE",
            "USER_AUTHORIZED_PRIVATE",
            "DECLARED_USER_AUTHORIZED",
        ),
    ).record
    key = "ws-suti:" + digest(common)
    registered = base.source(project, source, POLICY, key + ":source")
    decisions = []
    # The source claim is that the frozen bytes contain the supplied concept
    # identity/label. It never certifies that the label is the poem's true meaning.
    for i, c in enumerate(common["concepts"]):
        term = {
            "predicate": "field_equals",
            "source_id": sid,
            "pointer": f"/concepts/{i}/label",
            "value": c["label"],
        }
        scope = {
            "task_id": key + ":" + str(i),
            "scope_version": 1,
            "source_snapshots": {sid: digest(source)},
            "boundary": "Frozen annotation field bytes only; interpretation remains unverified",
            "execution_permission": False,
        }
        task = {
            "task_id": scope["task_id"],
            "claim_kind": "SOURCE_CLAIM",
            "source_ids": [sid],
            "record_ids": [sid],
            "assumptions": [
                "Caller explicitly supplied this exact frozen annotation.",
                "No author-intention, truth, physical or native SUTI claim.",
            ],
            "scope": scope,
            "allowed_predicates": ["field_equals"],
            "question": "Is the declared annotation label exactly stored at this address?",
        }
        t = base.task(
            project,
            {"schema": "lm-suti.assurance.task/0.1", "project": project, "task": task},
            key + f":task:{i}",
        )
        base.review(
            project,
            t["task_ref"],
            "OWNER_FROZEN_INGRESS_SCOPE",
            "Exact caller-provided snapshot, annotation-field checks only, no truth review.",
            key + f":review:{i}",
        )
        candidate = {
            "schema": "symseq.assurance.candidate.v1",
            "candidate_id": scope["task_id"],
            "task_id": scope["task_id"],
            "claim_kind": "SOURCE_CLAIM",
            "assertion": {
                "language": "source-claim-v1",
                "content": canonical(term),
                "machine_term": term,
            },
            "scope": scope,
            "assumptions": task["assumptions"],
            "source_refs": [core.contracts.source_ref(source)],
            "evidence_refs": ["sha256:" + digest(source)],
            "proposed_status": "SOURCE_ATTESTED",
            "generator": {
                "kind": "OTHER",
                "id": BACKEND,
                "config_digest": digest({"adapter": BACKEND}),
            },
        }
        c_ref = base.candidate(
            project,
            {
                "schema": "lm-suti.assurance.candidate/0.1",
                "project": project,
                "task_ref": t["task_ref"],
                "format": "candidate",
                "raw": canonical(candidate),
            },
            key + f":candidate:{i}",
        )
        checked = base.check(
            project, c_ref["candidate_ref"], "direct", key + f":check:{i}"
        )
        decisions.append(
            {
                "concept_id": c["id"],
                "check_ref": checked["check_ref"],
                "status": checked["status"],
                "scope": "DECLARED_ANNOTATION_LABEL_BYTES_ONLY",
            }
        )
    return build_output(common, common_ref, slots, registered["source_ref"], decisions)


def build_output(common, common_ref, slots, source_ref, decisions):
    frames = []
    for c in common["concepts"][:slots]:
        frames.append(
            {
                "id": f"F{len(frames)+1:02}",
                "concepts": [c],
                "source_relations": [
                    r for r in common["source_relations"] if c["id"] in r["concepts"]
                ],
                "interpretation_status": "UNKNOWN",
                "origin": "UNCHANGED_DECLARED_INPUT_NO_NEW_RELATIONS",
            }
        )
    projection = {
        "schema": "levinmas-suti-projection/1",
        "uses": [
            "source",
            "concepts.id",
            "concepts.label",
            "concepts.evidence",
            "source_relations",
            "uncertainties",
        ],
        "drops": [],
        "adds": ["source-byte assurance receipts", "explicit task scope"],
        "coordinates_used": False,
        "backend": BACKEND,
        "SUTI_native_runtime": "NOT_EXECUTED",
    }
    return {
        "schema": "levinmas-suti-frozen-result/1",
        "engine": "suti",
        "backend": BACKEND,
        "SUTI_native_runtime": "NOT_EXECUTED",
        "common_snapshot": common,
        "common_snapshot_sha256": digest(common),
        "common_snapshot_ref": common_ref,
        "source_sha256": common["source"]["sha256"],
        "projection": projection,
        "projection_sha256": digest(projection),
        "assurance_source_ref": source_ref,
        "decisions": decisions,
        "frames": frames,
        "selected_frames": frames,
        "decoder_packet": {
            "schema": "levinmas-suti-decoder/1",
            "source": common["source"],
            "concepts": common["concepts"],
            "source_relations": common["source_relations"],
            "uncertainties": common["uncertainties"],
            "frames": frames,
            "missing_slots": max(0, slots - len(frames)),
            "boundary": "Only declared concepts/relations and actual source assurance; no hidden extraction or native SUTI",
        },
        "summary": {
            "steps": len(decisions),
            "source_assurance_checks": len(decisions),
            "frames": len(frames),
            "decoded_frame_slots": len(frames),
            "missing_slots": max(0, slots - len(frames)),
            "model_calls": 0,
            "tokens": None,
            "cost_USD": None,
            "numeric_projections": None,
        },
        "semantic_fidelity": "UNASSESSED",
        "execution_permission": False,
    }
