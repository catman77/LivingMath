"""Resolve an actual same-project immutable symbolic candidate, never caller ASTs."""

from pathlib import Path
from ..core import digest
from ..symbolic.state import require
from ..symbolic.kernel import binding
from ..symbolic.service import SymbolicService
from ..white_star import blobs
from .composition_ast import ast_metrics


def semantic_train(records: list[dict]) -> list[dict]:
    values = [{"tokens": r["tokens"], "accepted": r["accepted"]} for r in records]
    return sorted(values, key=digest)


def resolve(root: str | Path, project: str, run_id: str, train: list[dict]) -> dict:
    workspace, record = SymbolicService(root, None).load(project, run_id)
    require(record["status"] == "COMPLETED", "SOURCE_NOT_COMPLETED")
    require(
        record["kernel_binding"] == binding(),
        "SOURCE_KERNEL_NOT_COMPATIBLE",
        "/source_run_id",
    )
    request = workspace.get(record["input_ref"])
    artifact = blobs.get(workspace, record["result_ref"])
    require(
        digest(request)
        == record["input_ref"]
        == artifact["manifest"]["request_digest"],
        "SOURCE_INPUT_MISMATCH",
        "/source_run_id",
    )
    require(
        artifact["input"] == request
        and digest(artifact) == record["result_digest"]
        and artifact["manifest"]["kernel_binding"] == record["kernel_binding"],
        "SOURCE_RESULT_MISMATCH",
        "/source_run_id",
    )
    models = artifact.get("grammar_hypotheses") or []
    require(len(models) == 1, "SOURCE_CANDIDATE_NOT_COMPATIBLE", "/source_run_id")
    model = models[0]
    require(
        artifact["manifest"]["artifact_digests"]["grammar_hypotheses"]
        == digest(models),
        "SOURCE_AST_MISMATCH",
        "/source_run_id",
    )
    require(
        digest(model["train_samples"]) == model["train_digest"],
        "SOURCE_TRAIN_MISMATCH",
        "/source_run_id",
    )
    expected = semantic_train(train)
    require(
        expected
        == semantic_train(model["train_samples"])
        == semantic_train(request["task"]["train"]),
        "SOURCE_TRAIN_MISMATCH",
        "/source_run_id",
    )
    ast = model.get("relational_rule_ast")
    require(
        model.get("selected_formalism") == "observed_relation_composition"
        and isinstance(ast, dict),
        "SOURCE_CANDIDATE_NOT_COMPATIBLE",
        "/source_run_id",
    )
    require(
        digest(ast) == model["selected_candidate_id"],
        "SOURCE_AST_MISMATCH",
        "/source_run_id",
    )
    require(
        any(
            c.get("candidate_id") == digest(ast) and c.get("ast") == ast
            for c in model["train_compatible_candidates"]
        ),
        "SOURCE_AST_MISMATCH",
        "/source_run_id",
    )
    try:
        ast_metrics(ast)
    except (ValueError, KeyError, TypeError):
        require(False, "SOURCE_CANDIDATE_NOT_COMPATIBLE", "/source_run_id")
    proof = {
        "source_run_id": run_id,
        "source_input_digest": record["input_ref"],
        "source_result_digest": record["result_digest"],
        "source_kernel_binding": record["kernel_binding"],
        "source_ast_digest": digest(ast),
        "source_train_digest": model["train_digest"],
        "train_semantic_digest": digest(expected),
    }
    return {"candidates": [{"ast": ast, "ast_digest": digest(ast)}], "binding": proof}
