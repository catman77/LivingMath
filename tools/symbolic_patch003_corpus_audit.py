"""Independent byte-level corpus hierarchy audit; does not fit or inspect holdout labels."""

import argparse, hashlib, json, re
from pathlib import Path
from collections import Counter, defaultdict
from lm_suti_assurance.core import digest
from lm_suti_assurance.observer_synthesis.data import validate_record


def check(value, message):
    if not value:
        raise ValueError(message)


def alpha(lines, local=False):
    names = {}
    result = []
    for line in lines:
        if local:
            names = {}
        row = []
        for token in line:
            if token not in names:
                names[token] = str(len(names))
            row.append(names[token])
        result.append(row)
    return result


def audit_pair(records, source, source_ref):
    """Trace source-carrier projection and each permuted word to actual parent bytes."""
    raw = source["text"].encode()
    check(hashlib.sha256(raw).hexdigest() == source["sha256"], "PARENT_SOURCE_HASH")
    check(len(records) == 2, "PAIR_CARDINALITY")
    m = records[0]["metadata"]
    a, b = m["parent_byte_start"], m["parent_byte_end"]
    check(0 <= a < b <= len(raw), "PARENT_SOURCE_SPAN")
    original_text = raw[a:b].decode()
    original_lines = original_text.splitlines()
    check(len(original_lines) == 4, "FOUR_SOURCE_LINES_REQUIRED")
    offsets = []
    cursor = a
    for line in original_lines:
        offsets.append(cursor)
        cursor += len(line.encode()) + 1
    variants = []
    for r in records:
        validate_record(r, "train" if "accepted" in r else "queries")
        check(
            r["metadata"] == m and m["parent_source_ref"] == source_ref,
            "PARENT_SOURCE_REF",
        )
        check(
            r["source"]["edition"] == source["edition"]
            and r["source"]["rights"] == source["rights"],
            "EDITION_OR_RIGHTS_CHANGED",
        )
        byid = {s["id"]: s for s in r["segments"]}
        roots = [s for s in byid.values() if s["kind"] == "century"]
        poems = [s for s in byid.values() if s["kind"] == "quatrain"]
        lines = [s for s in byid.values() if s["kind"] == "line"]
        words = [s for s in byid.values() if s["kind"] == "word"]
        check(
            len(roots) == len(poems) == 1 and roots[0]["parent_id"] is None,
            "CENTURY_PROJECTION",
        )
        check(
            poems[0]["parent_id"] == roots[0]["id"] and len(lines) == 4,
            "QUATRAIN_LINE_TREE",
        )
        check(
            roots[0]["byte_start"] == poems[0]["byte_start"] == 0
            and roots[0]["byte_end"]
            == poems[0]["byte_end"]
            == len(r["source"]["text"].encode()),
            "PROJECTED_CARRIER_SPAN",
        )
        order = [0, 1, 2, 3] if r["source"]["text"] == original_text else [0, 2, 1, 3]
        check(
            r["source"]["text"] == "\n".join(original_lines[i] for i in order),
            "UNKNOWN_TEXT_VARIANT",
        )
        carrier = r["source"]["text"].encode()
        line_nodes = []
        local_offset = 0
        for line_index, segment in enumerate(lines):
            check(segment["parent_id"] == poems[0]["id"], "LINE_PARENT")
            expected = original_lines[order[line_index]]
            check(
                segment["byte_start"] == local_offset
                and segment["byte_end"] == local_offset + len(expected.encode()),
                "LINE_BYTE_SPAN",
            )
            check(
                carrier[segment["byte_start"] : segment["byte_end"]].decode()
                == expected,
                "LINE_CONTENT",
            )
            children = [s for s in words if s["parent_id"] == segment["id"]]
            matches = list(re.finditer(r"\S+", expected))
            check(len(children) == len(matches), "WORD_COUNT")
            word_nodes = []
            for s, match in zip(children, matches):
                begin = len(expected[: match.start()].encode())
                end = len(expected[: match.end()].encode())
                check(
                    (s["byte_start"], s["byte_end"])
                    == (local_offset + begin, local_offset + end),
                    "WORD_BYTE_SPAN",
                )
                start_parent = offsets[order[line_index]] + begin
                end_parent = offsets[order[line_index]] + end
                check(
                    raw[start_parent:end_parent].decode() == match.group(),
                    "WORD_PARENT_SOURCE_SLICE",
                )
                word_nodes.append(
                    {
                        "kind": "word",
                        "carrier_segment_id": s["id"],
                        "text_sha256": hashlib.sha256(
                            match.group().encode()
                        ).hexdigest(),
                        "parent_byte_span": [start_parent, end_parent],
                        "carrier_byte_span": [s["byte_start"], s["byte_end"]],
                    }
                )
            line_nodes.append(
                {
                    "kind": "line",
                    "carrier_segment_id": segment["id"],
                    "source_line_index": order[line_index],
                    "parent_byte_span": [
                        offsets[order[line_index]],
                        offsets[order[line_index]] + len(expected.encode()),
                    ],
                    "words": word_nodes,
                }
            )
            local_offset += len(expected.encode()) + 1
        check(
            sum(len(x["words"]) for x in line_nodes) == len(r["tokens"]),
            "UNPARENTED_WORD",
        )
        variants.append(
            {
                "record_id": r["id"],
                "pair_id": r["pair_id"],
                "carrier_sha256": r["source"]["sha256"],
                "source_ref": source_ref,
                "source_sha256": source["sha256"],
                "parent_byte_span": [a, b],
                "edition": source["edition"],
                "variant_line_order": order,
                "record_local_century_segment": "projection into one quatrain carrier, not full-century text",
                "global_alpha": alpha(r["lines"]),
                "local_alpha": alpha(r["lines"], True),
                "lines": line_nodes,
            }
        )
    check(
        {tuple(v["variant_line_order"]) for v in variants}
        == {(0, 1, 2, 3), (0, 2, 1, 3)},
        "BOTH_VARIANTS_REQUIRED",
    )
    return variants


def audit(frozen, sources, output):
    train = json.loads((frozen / "train.json").read_text())
    queries = json.loads((frozen / "queries.json").read_text())
    protocol = json.loads((frozen / "FROZEN_PROTOCOL.json").read_text())
    check(
        digest(train) == protocol["train_digest"]
        and digest(queries) == protocol["query_digest"],
        "FROZEN_DATA_HASH",
    )
    check(all("accepted" not in r for r in queries), "HELDOUT_LABEL_LEAKAGE")
    parents = {}
    centuries = defaultdict(list)
    for file in sorted(sources.glob("*.json")):
        data = json.loads(file.read_text())
        ref = data["record"]["input_ref"]
        check(digest(data["input"]) == ref, "INPUT_REF_HASH")
        source = data["input"]["source"]
        check(
            hashlib.sha256(source["text"].encode()).hexdigest() == source["sha256"],
            "SOURCE_HASH",
        )
        parents[ref] = source
        centuries[int(data["archive_fixture"]["century"])].append(
            {
                "source_ref": ref,
                "source_sha256": source["sha256"],
                "byte_span": [0, len(source["text"].encode())],
                "edition": source["edition"],
                "rights": source["rights"],
            }
        )
    grouped = defaultdict(list)
    for r in train + queries:
        c, n = r["metadata"]["century"], r["metadata"]["quatrain"]
        check((c <= 8) == ("accepted" in r), "CENTURY_SPLIT")
        check(r["pair_id"] == digest(["pair", c, n])[:24], "PAIR_ID_BINDING")
        grouped[(c, n)].append(r)
    check(
        len(grouped) == 942
        and len(train) == 1484
        and len(queries) == 400
        and len(parents) == 19,
        "CORPUS_CARDINALITY",
    )
    checked = []
    counts = Counter()
    pairids = set()
    from lm_suti_assurance.observer_synthesis.features import encode

    for (c, n), records in sorted(grouped.items()):
        ref = records[0]["metadata"]["parent_source_ref"]
        variants = audit_pair(records, parents[ref], ref)
        for r, v in zip(records, variants):
            check(
                encode(r, "global_alpha")["lines"] == v["global_alpha"],
                "PER_VARIANT_GLOBAL_ALPHA",
            )
            check(
                encode(r, "local_alpha")["lines"] == v["local_alpha"],
                "PER_VARIANT_LOCAL_ALPHA",
            )
        equal = variants[0]["global_alpha"] == variants[1]["global_alpha"]
        counts["global_alpha_identical_pairs"] += equal
        pairids.add(records[0]["pair_id"])
        checked.append(
            {
                "kind": "quatrain",
                "century": c,
                "number": n,
                "pair_id": records[0]["pair_id"],
                "source_ref": ref,
                "source_sha256": parents[ref]["sha256"],
                "variants": variants,
            }
        )
    check(
        len(pairids) == 942 and counts["global_alpha_identical_pairs"] == 78,
        "PAIR_ALPHA_COUNTS",
    )
    tree = [
        {
            "kind": "century",
            "number": c,
            "source_chunks": chunks,
            "children": [q for q in checked if q["century"] == c],
        }
        for c, chunks in sorted(centuries.items())
    ]
    result = {
        "status": "PASS",
        "schema": "patch003-source-bound-corpus-audit/1",
        "quatrains": 942,
        "pairs": 942,
        "variants": 1884,
        "source_chunks": 19,
        "train_records": 1484,
        "query_records": 400,
        "external_labels_read": False,
        "century_counts": dict(Counter(c for c, n in grouped)),
        "global_alpha_identical_pairs": counts["global_alpha_identical_pairs"],
        "record_segments_scope": "century is a record-local projection; this global tree supplies the full actual source-chunk ancestry",
        "edition_policy": "All original mixed-edition bytes and anomalies retained; no critical-edition claim",
        "anomalies": protocol["anomalies"],
        "frozen_protocol_digest": digest(protocol),
        "source_tree": tree,
    }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in ["source_tree", "anomalies"]}
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--frozen", type=Path, required=True)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    a = parser.parse_args()
    audit(a.frozen, a.sources, a.output)
