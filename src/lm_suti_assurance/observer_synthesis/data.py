"""Dataset validation has no access to external label files or arbitrary paths."""

import hashlib
from ..core import digest
from ..symbolic.state import require
from ..white_star.contracts import check_schema
from ..symbolic_complex.contracts import validate
from .contracts import DATASET, TRAIN, RECORD


def dataset_payload(dataset):
    return {k: v for k, v in dataset.items() if k != "sha256"}


def validate_dataset(dataset):
    validate(dataset, DATASET)
    require(
        dataset["sha256"] == digest(dataset_payload(dataset)),
        "SOURCE_MISMATCH",
        "/dataset/sha256",
    )
    if dataset["kind"] == "collection":
        require(
            "records" not in dataset
            and bool(dataset.get("parts"))
            and "record_kind" in dataset,
            "INVALID_INPUT",
            "/dataset",
        )
        require(
            len(dataset["parts"]) == len(set(dataset["parts"])),
            "INVALID_INPUT",
            "/dataset/parts",
        )
        return dataset
    require(
        "parts" not in dataset
        and "record_kind" not in dataset
        and bool(dataset.get("records")),
        "INVALID_INPUT",
        "/dataset",
    )
    for index, record in enumerate(dataset["records"]):
        validate_record(record, dataset["kind"], f"/dataset/records/{index}")
    require(
        len({r["id"] for r in dataset["records"]}) == len(dataset["records"]),
        "DUPLICATE_RECORD_ID",
        "/dataset/records",
    )
    return dataset


def validate_record(record, kind, path="/record"):
    require(
        not (kind == "queries" and "accepted" in record),
        "HELDOUT_LABEL_LEAKAGE",
        path + "/accepted",
    )
    check_schema(record, TRAIN if kind == "train" else RECORD)
    source = record["source"]
    raw = source["text"].encode()
    require(len(raw) <= 48000, "SOURCE_LIMIT", path + "/source/text")
    require(
        hashlib.sha256(raw).hexdigest() == source["sha256"],
        "SOURCE_MISMATCH",
        path + "/source/sha256",
    )
    require(
        bool(source["rights"].strip()) and bool(source["edition"].strip()),
        "SOURCE_RIGHTS_REQUIRED",
        path + "/source/rights",
    )
    require(
        source["text"].split() == record["tokens"],
        "SPAN_TEXT_MISMATCH",
        path + "/tokens",
    )
    if "lines" in record:
        require(
            record["lines"] == [line.split() for line in source["text"].splitlines()],
            "BOUNDARY_MISMATCH",
            path + "/lines",
        )
    segments = {s["id"]: s for s in record.get("segments", [])}
    require(
        len(segments) == len(record.get("segments", [])),
        "DUPLICATE_SEGMENT",
        path + "/segments",
    )
    for ident, s in segments.items():
        a, b = s["byte_start"], s["byte_end"]
        require(0 <= a <= b <= len(raw), "INVALID_SPAN", path + "/segments/" + ident)
        try:
            raw[a:b].decode()
        except UnicodeError:
            require(False, "INVALID_SPAN", path + "/segments/" + ident)
        parent = s["parent_id"]
        seen = {ident}
        for _ in range(len(segments) + 1):
            if parent is None:
                break
            require(
                parent in segments and parent not in seen,
                "CYCLIC_OR_MISSING_SEGMENT",
                path + "/segments/" + ident,
            )
            seen.add(parent)
            p = segments[parent]
            require(
                p["byte_start"] <= a <= b <= p["byte_end"],
                "INVALID_PARENT_SPAN",
                path + "/segments/" + ident,
            )
            parent = p["parent_id"]
        else:
            require(False, "CYCLIC_SEGMENT", path + "/segments/" + ident)
    words = [s for s in record.get("segments", []) if s["kind"] == "word"]
    if words:
        require(
            [raw[s["byte_start"] : s["byte_end"]].decode() for s in words]
            == record["tokens"],
            "SPAN_TEXT_MISMATCH",
            path + "/segments",
        )
    return record
