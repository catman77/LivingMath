"""Independent finite proof checker. Never imports the complex constructor/reference.

H1 and path-coherence are distinct obligations. Flags in a submitted object are
not evidence: positions, incidences, chains, complete peaks and induction are read.
"""

import hashlib
from itertools import product, combinations
from ..core import digest
from ..errors import AssuranceError

VERSION = "SP-finite-independent-checker/1"


def rank_rows(columns, row_count):
    rows = [0] * row_count
    for j, indices in enumerate(columns):
        for i in indices:
            rows[i] ^= 1 << j
    basis = {}
    for row in rows:
        for _ in range(row.bit_length() + 1):
            if not row:
                break
            pivot = (row & -row).bit_length() - 1
            if pivot in basis:
                row ^= basis[pivot]
            else:
                basis[pivot] = row
                break
    return len(basis)


class Invalid(Exception):
    def __init__(self, code, path):
        self.code = code
        self.path = path


def need(ok, code, path):
    if not ok:
        raise Invalid(code, path)


def verify(data):
    try:
        return _verify(data)
    except (
        Invalid,
        KeyError,
        TypeError,
        ValueError,
        IndexError,
        AssuranceError,
    ) as exc:
        return {
            "status": "REJECTED",
            "pi1_status": "NOT_PROVED",
            "verifier_version": VERSION,
            "failed_obligations": [
                {
                    "code": getattr(exc, "code", "MALFORMED_CERTIFICATE"),
                    "field_path": getattr(exc, "path", "/certificate"),
                }
            ],
            "execution_permission": False,
        }


def _verify(data):
    request = data["input"]
    source = request["complex_source"]
    fixture = source["kind"] == "sp_balanced_fixture"
    need(
        fixture or source["kind"] == "saved_symbolic_history",
        "UNSUPPORTED_MODEL",
        "/input/complex_source/kind",
    )
    vertices = data["vertices"]
    edges = data["edges"]
    cells = data["cells"]
    need(
        len(vertices) <= 8192 and len(edges) <= 16384 and len(cells) <= 5000,
        "BUDGET_EXCEEDED",
        "/certificate",
    )
    v = {x["id"]: x for x in vertices}
    e = {x["id"]: x for x in edges}
    f = {x["id"]: x for x in cells}
    need(
        len(v) == len(vertices) and len(e) == len(edges) and len(f) == len(cells),
        "DUPLICATE_ID",
        "/certificate",
    )

    def check_id(record, kind, path):
        need(
            record["id"]
            == digest({"kind": kind, **{k: x for k, x in record.items() if k != "id"}}),
            "SOURCE_MISMATCH",
            path + "/id",
        )

    if fixture:
        n = source["max_length"]
        need(
            type(n) is int and n in (2, 4, 6, 8, 10),
            "UNSUPPORTED_MODEL",
            "/input/complex_source/max_length",
        )
        expected = {""}
        for length in range(2, n + 1, 2):
            expected.update(
                "".join(t)
                for t in product("PS", repeat=length)
                if t.count("S") == t.count("P")
            )
        words = {"".join(x["tokens"]): i for i, x in v.items()}
        need(
            set(words) == expected and len(words) == len(v),
            "INCOMPLETE_SP_VERTICES",
            "/vertices",
        )
        scope = digest(source)
        for i, x in v.items():
            check_id(x, "sp_vertex/1", "/vertices/" + i)
            w = "".join(x["tokens"])
            need(
                x["object_scope"] == scope
                and x["source_spans"]
                == [
                    {
                        "source_sha256": hashlib.sha256(w.encode()).hexdigest(),
                        "byte_start": 0,
                        "byte_end": len(w),
                    }
                ],
                "SOURCE_MISMATCH",
                "/vertices/" + i + "/source_spans",
            )
    else:
        words = {}
        verify_saved_source(data, v, e)
    out = {i: [] for i in v}
    d1 = []
    vindex = {i: j for j, i in enumerate(v)}
    eindex = {i: j for j, i in enumerate(e)}
    actual_positions = set()
    for i, x in e.items():
        need(x["src_id"] in v and x["dst_id"] in v, "UNVERIFIED_EDGE", "/edges/" + i)
        need(x.get("verified") is True, "UNVERIFIED_EDGE", "/edges/" + i + "/verified")
        check_id(x, "rewrite_edge/1", "/edges/" + i)
        if fixture:
            w = v[x["src_id"]]["tokens"]
            target = v[x["dst_id"]]["tokens"]
            k = x["match_span"]["token_start"]
            need(
                type(k) is int
                and 0 <= k < len(w) - 1
                and x["match_span"]["token_end"] == k + 2,
                "INVALID_EDGE_POSITION",
                "/edges/" + i + "/match_span",
            )
            pair = "".join(w[k : k + 2])
            need(
                pair in ("SP", "PS")
                and x["rule_id"] == pair + "_TO_EMPTY"
                and target == w[:k] + w[k + 2 :],
                "UNVERIFIED_EDGE",
                "/edges/" + i,
            )
            need(
                x["orientation"] == "forward" and len(target) == len(w) - 2,
                "NON_TERMINATING_EDGE",
                "/edges/" + i,
            )
            need(
                x["provenance"]
                == {
                    "generator_ref": scope,
                    "source_word_sha256": hashlib.sha256(
                        "".join(w).encode()
                    ).hexdigest(),
                    "rule_version": "SP-cancel/1",
                },
                "SOURCE_MISMATCH",
                "/edges/" + i + "/provenance",
            )
            need(
                (x["src_id"], k) not in actual_positions,
                "DUPLICATE_POSITIONAL_EDGE",
                "/edges/" + i,
            )
            actual_positions.add((x["src_id"], k))
        out[x["src_id"]].append(i)
        d1.append([vindex[x["src_id"]], vindex[x["dst_id"]]])
    if fixture:
        required = {
            (i, k)
            for i, x in v.items()
            for k in range(len(x["tokens"]) - 1)
            if x["tokens"][k] != x["tokens"][k + 1]
        }
        need(actual_positions == required, "INCOMPLETE_POSITIONAL_EDGES", "/edges")
    expected_peaks = {
        frozenset(pair): src
        for src, ids in out.items()
        for pair in combinations(ids, 2)
    }
    peaks = {x["id"]: x for x in data["peaks"]}
    need(len(peaks) == len(data["peaks"]), "DUPLICATE_PEAK", "/peaks")
    peak_by_pair = {}
    for i, x in peaks.items():
        check_id(x, "local_peak/1", "/peaks/" + i)
        pair = frozenset(x["edge_ids"])
        need(
            pair in expected_peaks
            and x["src_id"] == expected_peaks[pair]
            and pair not in peak_by_pair,
            "UNVERIFIED_PEAK",
            "/peaks/" + i,
        )
        peak_by_pair[pair] = i
    need(
        set(peak_by_pair) == set(expected_peaks), "INCOMPLETE_PEAK_INVENTORY", "/peaks"
    )

    def path(steps, start, field):
        at = start
        for j, s in enumerate(steps):
            need(
                s["edge_id"] in e and type(s["sign"]) is int and s["sign"] in (-1, 1),
                "UNVERIFIED_EDGE",
                field + "/" + str(j),
            )
            edge = e[s["edge_id"]]
            a, b = (
                (edge["src_id"], edge["dst_id"])
                if s["sign"] == 1
                else (edge["dst_id"], edge["src_id"])
            )
            need(a == at, "BROKEN_PATH", field + "/" + str(j))
            at = b
        return at

    complete = {}
    d2 = []
    for i, x in f.items():
        check_id(x, "coherence_cell/1", "/cells/" + i)
        need(x.get("verified") is True, "UNVERIFIED_CELL", "/cells/" + i + "/verified")
        a, b = x["left_path"], x["right_path"]
        need(a and b, "EMPTY_ATTACHING_PATH", "/cells/" + i)
        need(x["src_id"] in v and x["dst_id"] in v, "UNVERIFIED_CELL", "/cells/" + i)
        need(
            path(a, x["src_id"], "/cells/" + i + "/left_path")
            == path(b, x["src_id"], "/cells/" + i + "/right_path")
            == x["dst_id"],
            "CELL_ENDPOINT_MISMATCH",
            "/cells/" + i,
        )
        pair = frozenset((a[0]["edge_id"], b[0]["edge_id"]))
        need(
            len(pair) == 2 and pair in peak_by_pair and pair not in complete,
            "UNVERIFIED_CELL",
            "/cells/" + i + "/source_peak_id",
        )
        need(
            x["source_peak_id"] == peak_by_pair[pair],
            "UNVERIFIED_PEAK",
            "/cells/" + i + "/source_peak_id",
        )
        if fixture:
            need(
                all(s["sign"] == 1 for s in a + b)
                and len(a) == len(b) == (1 if x["role"] == "bigon" else 2),
                "UNVERIFIED_CELL",
                "/cells/" + i + "/role",
            )
            need(
                x["role"] in ("bigon", "diamond")
                and peaks[x["source_peak_id"]]["join_state"] == x["dst_id"],
                "UNVERIFIED_CELL",
                "/cells/" + i,
            )
            need(
                x["source_spans"] == v[x["src_id"]]["source_spans"]
                and x["rule_version"] == "SP-cancel/1"
                and x["completion_search_budget"] == 1,
                "SOURCE_MISMATCH",
                "/cells/" + i + "/source_spans",
            )
        complete[pair] = i
        indices = set()
        for step in a + b:
            idx = eindex[step["edge_id"]]
            if idx in indices:
                indices.remove(idx)
            else:
                indices.add(idx)
        column = sorted(indices)
        boundary = set()
        for j in column:
            for vertex in d1[j]:
                if vertex in boundary:
                    boundary.remove(vertex)
                else:
                    boundary.add(vertex)
        need(not boundary, "BOUNDARY_SQUARED_NONZERO", "/cells/" + i)
        d2.append(column)
    r1 = rank_rows(d1, len(v))
    r2 = rank_rows(d2, len(e))
    components = len(v) - r1
    beta = len(e) - len(v) + components
    h1 = beta - r2
    homology = data["homology"]
    need(
        homology["field"] == "F2"
        and homology["boundary_d1"] == d1
        and homology["boundary_d2"] == d2,
        "CHAIN_CERTIFICATE_MISMATCH",
        "/homology",
    )
    need(
        (homology["rank_d1"], homology["rank_d2_F2"], homology["H1_dim"])
        == (r1, r2, h1),
        "RANK_CERTIFICATE_MISMATCH",
        "/homology",
    )
    basis = homology["basis_cell_ids"]
    need(
        len(basis) == len(set(basis)) == r2 and set(basis) <= set(f),
        "BAD_HOMOLOGY_BASIS",
        "/homology/basis_cell_ids",
    )
    findex = {i: j for j, i in enumerate(f)}
    need(
        rank_rows([d2[findex[i]] for i in basis], len(e)) == r2,
        "BAD_HOMOLOGY_BASIS",
        "/homology/basis_cell_ids",
    )
    missing = set(expected_peaks) - set(complete)
    proof = data.get("paths")
    status = "NOT_PROVED"
    failed = []
    if not fixture:
        failed = [
            {"code": "NO_SP_PATH_CERTIFICATE_FOR_SAVED_HISTORY", "field_path": "/paths"}
        ]
    elif request["cells"]["policy"] != "all_local_peaks" or missing or proof is None:
        failed = [
            {
                "code": (
                    "MISSING_LOCAL_PEAK_CELLS"
                    if missing
                    else "PATH_CERTIFICATE_NOT_SUPPLIED"
                ),
                "field_path": "/cells",
                "missing_peaks": len(missing),
            }
        ]
    else:
        need(
            proof["algorithm"] == "strict-length-induction-on-canonical-SP-paths/1"
            and set(proof["assumptions"])
            == {"all_local_peaks_filled", "terminating_SP_rewriting"},
            "UNSUPPORTED_CERTIFICATE",
            "/paths",
        )
        empty = words[""]
        need(
            proof["base_vertex"] == empty and components == 1,
            "BAD_BASEPOINT",
            "/paths/base_vertex",
        )
        canonical = {
            i: min(ids, key=lambda eid: e[eid]["match_span"]["token_start"])
            for i, ids in out.items()
            if ids
        }
        need(
            set(proof["canonical_paths"]) == set(v),
            "INCOMPLETE_CANONICAL_PATHS",
            "/paths/canonical_paths",
        )
        for src, ids in proof["canonical_paths"].items():
            need(
                path(
                    [{"edge_id": x, "sign": 1} for x in ids],
                    src,
                    "/paths/canonical_paths/" + src,
                )
                == empty,
                "BAD_CANONICAL_PATH",
                "/paths/canonical_paths/" + src,
            )
            at = src
            for eid in ids:
                need(
                    eid == canonical[at],
                    "NON_CANONICAL_EDGE",
                    "/paths/canonical_paths/" + src,
                )
                at = e[eid]["dst_id"]
        lemmas = {x["edge_id"]: x for x in proof["lemmas"]}
        need(
            len(lemmas) == len(proof["lemmas"]) == len(e) and set(lemmas) == set(e),
            "INCOMPLETE_PROOF_DAG",
            "/paths/lemmas",
        )
        checked = set()
        for eid in sorted(e, key=lambda x: (len(v[e[x]["src_id"]]["tokens"]), x)):
            edge = e[eid]
            lemma = lemmas[eid]
            canon = canonical[edge["src_id"]]
            need(
                lemma["canonical_edge_id"] == canon,
                "BAD_CANONICAL_EDGE",
                "/paths/lemmas/" + eid,
            )
            if eid == canon:
                need(
                    lemma["case"] == "canonical"
                    and lemma["cell_id"] is None
                    and lemma["dependencies"] == [],
                    "BAD_BASE_LEMMA",
                    "/paths/lemmas/" + eid,
                )
            else:
                cell_id = complete[frozenset((eid, canon))]
                cell = f[cell_id]
                dependencies = [
                    s["edge_id"]
                    for branch in (cell["left_path"], cell["right_path"])
                    for s in branch[1:]
                ]
                need(
                    lemma["case"] == "local_peak"
                    and lemma["cell_id"] == cell_id
                    and lemma["dependencies"] == dependencies,
                    "BAD_LOCAL_PEAK_LEMMA",
                    "/paths/lemmas/" + eid,
                )
                need(
                    all(
                        dep in checked
                        and len(v[e[dep]["src_id"]]["tokens"])
                        < len(v[edge["src_id"]]["tokens"])
                        for dep in dependencies
                    ),
                    "CYCLIC_OR_NONDECREASING_PROOF",
                    "/paths/lemmas/" + eid + "/dependencies",
                )
            checked.add(eid)
        status = "PROVED_TRIVIAL_WITH_CERTIFICATE"
    result = {
        "status": "CHECKED_INSTANCE" if status.startswith("PROVED_") else "NOT_PROVED",
        "pi1_status": status,
        "components": components,
        "graph_beta1": beta,
        "rank_d1": r1,
        "rank_d2_F2": r2,
        "H1_dim": h1,
        "boundary_squared_zero": True,
        "missing_peaks": len(missing),
        "verifier_version": VERSION,
        "verified_edge_count": len(e),
        "verified_cell_count": len(f),
        "failed_obligations": failed,
        "execution_permission": False,
    }
    result["verifier_digest"] = digest(result)
    return result


def verify_saved_source(data, vertices, edges):
    from ..symbolic.state import History, SymbolicState, Atom, apply, source_states

    artifact = data["source_artifact"]
    history = History()
    raw = {s["node_id"]: s for s in artifact["states"]}
    for node in artifact["history"]:
        value = raw[node["node_id"]]
        state = SymbolicState(
            tuple(
                Atom(t, tuple(tuple(span) for span in spans))
                for t, spans in zip(value["tokens"], value["source_spans"])
            ),
            tuple(tuple(b) for b in value["boundaries"]),
        )
        ident = history.add(
            state, node["parent_ids"], node["op"], node["op_args"], node["events"]
        )
        need(
            ident == node["node_id"] and digest(history.nodes[ident]) == digest(node),
            "SOURCE_MISMATCH",
            "/source_artifact/history",
        )
    need(history.verify(), "SOURCE_MISMATCH", "/source_artifact/history")
    original = History()
    _, _, source_map = source_states(artifact["input"], original)
    need(
        digest(source_map) == digest(artifact["source_map"])
        and all(
            i in history.states and s == history.states[i]
            for i, s in original.states.items()
        ),
        "SOURCE_MISMATCH",
        "/source_artifact/source_map",
    )
    lineage = {v["lineage_ref"]: v for v in vertices.values()}
    need(set(lineage) == set(raw), "SOURCE_MISMATCH", "/vertices")
    for old, v in lineage.items():
        need(
            v["object_scope"] == digest(data["input"]["complex_source"])
            and v["tokens"] == raw[old]["tokens"]
            and v["source_spans"] == raw[old]["source_spans"],
            "SOURCE_MISMATCH",
            "/vertices/" + v["id"],
        )
        need(
            v["id"]
            == digest(
                {"kind": "saved_vertex/1", **{k: x for k, x in v.items() if k != "id"}}
            ),
            "SOURCE_MISMATCH",
            "/vertices/" + v["id"],
        )
    actual = {
        n["node_id"]: n
        for n in artifact["history"]
        if n["op"]
        in {
            "CONCAT",
            "SPLIT",
            "RENAME",
            "SUBSTITUTE",
            "REVERSE",
            "SP_INV",
            "REDUCE_SP",
            "INSERT_CANCEL_PAIR",
        }
    }
    need(len(actual) == len(edges), "MISSING_SAVED_EDGES", "/edges")
    for edge in edges.values():
        ident = edge["provenance"]["history_node_id"]
        need(ident in actual, "UNVERIFIED_EDGE", "/edges/" + edge["id"])
        node = actual[ident]
        parent = node["parent_ids"][0]
        other = (
            history.states[node["parent_ids"][1]] if node["op"] == "CONCAT" else None
        )
        outputs, events = apply(
            history.states[parent], node["op"], node["op_args"], other
        )
        part = node["op_args"].get("output_part", 0)
        need(
            0 <= part < len(outputs)
            and outputs[part] == history.states[ident]
            and list(events) == node["events"],
            "UNVERIFIED_EDGE",
            "/edges/" + edge["id"],
        )
        need(
            edge["orientation"] == "forward"
            and edge["match_span"] == {"source_event_ranges": node["events"]}
            and edge["src_id"] == lineage[parent]["id"]
            and edge["dst_id"] == lineage[ident]["id"]
            and edge["rule_id"] == node["op"],
            "UNVERIFIED_EDGE",
            "/edges/" + edge["id"],
        )
        need(
            edge["provenance"]
            == {
                "history_node_id": ident,
                "parent_ids": node["parent_ids"],
                "op_args": node["op_args"],
                "source_artifact_digest": digest(artifact),
            },
            "SOURCE_MISMATCH",
            "/edges/" + edge["id"] + "/provenance",
        )
