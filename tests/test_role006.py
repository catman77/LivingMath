import copy, hashlib, itertools, json
import pytest
from lm_suti_assurance.core import digest


def rec(w, y=None):
    t = " ".join(w)
    r = {
        "id": digest(w),
        "tokens": list(w),
        "source": {
            "text": t,
            "sha256": hashlib.sha256(t.encode()).hexdigest(),
            "rights": "ORIGINAL_TEST_FIXTURE",
            "edition": "ROLE006/1",
        },
    }
    if y is not None:
        r["accepted"] = y
    return r


def oracle(w):
    depth = 0
    for t in w:
        depth += 1 if t == "S" else -1
        if depth < 0:
            return False
    return depth == 0


def samples(lengths):
    return [
        rec(list(w), oracle(w))
        for n in lengths
        for w in itertools.product("SP", repeat=n)
    ]


def request():
    from pathlib import Path

    q = json.loads(
        (Path(__file__).parent / "fixtures/generator005_request.json").read_text()
    )
    q["promotion_policy"]["mode"] = "role_branching_ast"
    q["promotion_policy"]["candidate_sources"] = ["derivation_trace"]
    return q


def test_generated_branching_full_corpus_and_two_nonempty_children():
    from lm_suti_assurance.observer_synthesis.learner import fit, predict

    m = fit(samples([2, 4, 6]), request())
    f = next(
        f for f in m["feature_registry"] if f["feature_id"] in m["used_feature_ids"]
    )
    assert (
        f["template_origin"] == "ROLE_BRANCHING_PROMOTION"
        and f["verifier_result"]["status"] == "CHECKED_INSTANCE"
    )
    assert f["operator_ast"]["roles"] == {"OPEN": "S", "CLOSE": "P"}
    from lm_suti_assurance.observer_synthesis.role_ast import execute

    proof = execute(
        f["operator_ast"], rec(list("SSPPSP")), f["known_invariance_scope"]
    )[1]
    assert [x["tokens"] for x in proof["tree"]["children"]] == [list("SP"), list("SP")]
    q = [rec(list(w)) for w in itertools.product("SP", repeat=8)]
    p = predict(m, q)["predictions"]
    assert all((r["score"] >= 0.5) == oracle(rw["tokens"]) for r, rw in zip(p, q))


def fitted(lengths=(2, 4, 6), options=None):
    from lm_suti_assurance.observer_synthesis.learner import fit

    q = request()
    q["promotion_policy"].update(options or {})
    train = samples(lengths)
    m = fit(train, q)
    f = next(
        f for f in m["feature_registry"] if f["feature_id"] in m["used_feature_ids"]
    )
    return train, m, f


@pytest.mark.parametrize(
    "mutation",
    [
        "role",
        "split",
        "branch",
        "span",
        "hash",
        "NF",
        "dp",
        "cell_missing",
        "claim",
        "outer",
    ],
)
def test_rehashed_positive_and_negative_forgery_rejected(mutation, monkeypatch):
    from lm_suti_assurance.observer_synthesis.role_ast import execute
    from lm_suti_assurance.observer_synthesis.role_checker import verify_proof

    _, m, f = fitted()
    r = rec(list("PS") if mutation in ["dp", "cell_missing"] else list("SSPPSP"))
    _, p = execute(f["operator_ast"], r, f["known_invariance_scope"])
    if mutation == "role":
        p["tree"]["roles"][0]["role"] = "CLOSE"
    elif mutation == "split":
        p["tree"]["trace"][0]["args"]["position"] += 1
    elif mutation == "branch":
        p["tree"]["children"].pop()
    elif mutation == "span":
        next(v for v in p["states"].values() if v["source_spans"])["source_spans"][0][
            0
        ][2] += 1
    elif mutation == "hash":
        p["tree"]["trace"][0]["output_word_hashes"][0] = "0" * 64
    elif mutation == "NF":
        p["tree"] = {"normal_form": []}
    elif mutation == "dp":
        p["cells"][-1]["value"] = True
    elif mutation == "cell_missing":
        p["cells"].pop()
    elif mutation == "claim":
        p["universal_invariant"] = True
    else:
        p["decision"] = 1
    # There is no trusted wrapper digest: re-hashing does not restore semantics.
    digest(p)
    monkeypatch.setattr(
        "lm_suti_assurance.observer_synthesis.role_ast.execute",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("solver used by checker")),
    )
    result = verify_proof(f["operator_ast"], r, f["known_invariance_scope"], p)
    assert result["status"] == "REJECTED" and not result["execution_permission"]


def test_unicode_roles_and_fixed_versus_covariant_rename():
    from lm_suti_assurance.observer_synthesis.role_ast import execute
    from lm_suti_assurance.observer_synthesis.role_checker import verify_proof

    _, _, f = fitted()
    p = f["operator_ast"]
    d = f["known_invariance_scope"]
    assert (
        execute(p, rec(list("SP")), d)[0] is True
        and execute(p, rec(list("PS")), d)[0] is False
    )
    renamed = copy.deepcopy(p)
    renamed["roles"] = {"OPEN": "кот", "CLOSE": "лес"}
    r = rec(["кот", "кот", "лес", "лес", "кот", "лес"])
    v, proof = execute(renamed, r, d)
    assert v and verify_proof(renamed, r, d, proof)["status"] == "CHECKED_INSTANCE"


@pytest.mark.parametrize(
    "limit,value,word",
    [
        ("max_cells", 2, "SSPPSP"),
        ("max_split_trials", 1, "SSPPSP"),
        ("max_depth", 1, "SSSSPPPP"),
        ("max_tokens", 4, "SSPPSP"),
    ],
)
def test_bounds_never_become_false_or_checked(limit, value, word):
    from lm_suti_assurance.observer_synthesis.role_ast import execute
    from lm_suti_assurance.observer_synthesis.role_checker import verify_proof

    _, _, f = fitted()
    d = copy.deepcopy(f["known_invariance_scope"])
    d[limit] = value
    r = rec(list(word))
    v, p = execute(f["operator_ast"], r, d)
    assert v is None and verify_proof(f["operator_ast"], r, d, p)["status"] == "UNKNOWN"


def test_minimal_oriented_pair_has_rivals_not_unique_grammar():
    from lm_suti_assurance.observer_synthesis.learner import fit

    m = fit([rec(list("SP"), True), rec(list("PS"), False)], request())
    d = m["role_diagnostics"]
    assert d["catalog"]["compatible"] > 1 and any(
        x["counterexamples"] for x in d["candidates"]
    )
    assert m["identifiability_status"] == "UNDERDETERMINED"


def test_full_negative_interval_table_and_empty_input_are_independent():
    from lm_suti_assurance.observer_synthesis.role_ast import execute
    from lm_suti_assurance.observer_synthesis.role_checker import verify_proof

    _, _, f = fitted()
    for word in ["", "SP", "PS", "SSPPSP", "PPSS", "SSSSPPPP"]:
        r = rec(list(word))
        value, p = execute(f["operator_ast"], r, f["known_invariance_scope"])
        v = verify_proof(f["operator_ast"], r, f["known_invariance_scope"], p)
        assert (
            value == oracle(word)
            and v["status"] == "CHECKED_INSTANCE"
            and len(p["cells"]) == (len(word) + 1) * (len(word) + 2) // 2
        )


def test_feature_identity_and_full_train_corruption(monkeypatch):
    from lm_suti_assurance.observer_synthesis.role_checker import verify
    from lm_suti_assurance.observer_synthesis.features import encode

    train, m, f = fitted()
    s = [{"record": r, "encoded": encode(r, "literal")} for r in train]
    assert verify(f, s)["status"] == "CHECKED_INSTANCE"
    bad = copy.deepcopy(f)
    bad["construction_trace"].pop()
    bad["witness_set_digest"] = digest(bad["construction_trace"])
    bad["digest"] = digest({k: v for k, v in bad.items() if k != "digest"})
    assert verify(bad, s)["status"] == "REJECTED"
    bad = copy.deepcopy(f)
    bad["origin"] = "BUILTIN"
    assert verify(bad, s)["status"] == "REJECTED"


def test_role_mode_rejects_alpha_collapse_and_effective_ablation():
    from lm_suti_assurance.observer_synthesis.learner import fit

    tr, m, f = fitted()
    for parent in [f["feature_id"], *f["parent_feature_refs"]]:
        q = request()
        q["feature_policy"]["feature_denylist"].append(parent)
        x = fit(tr, q)
        assert f["feature_id"] not in x["enabled_feature_ids"]
    q = request()
    q["feature_policy"]["representation"] = "global_alpha"
    x = fit(tr, q)
    assert not x["used_feature_ids"]


def test_predict_uses_independently_checked_bit_not_untrusted_scalar(monkeypatch):
    from lm_suti_assurance.observer_synthesis.learner import predict
    from lm_suti_assurance.observer_synthesis import role_ast

    _, m, f = fitted()
    original = role_ast.execute

    def liar(*args, **kwargs):
        bit, proof = original(*args, **kwargs)
        return not bit, proof

    monkeypatch.setattr(role_ast, "execute", liar)
    p = predict(m, [rec(list("PS")), rec(list("SP"))])["predictions"]
    assert p[0]["score"] < 0.5 and p[1]["score"] > 0.5
    assert (
        not p[0]["operator_evidence"][0]["decision"]
        and p[1]["operator_evidence"][0]["decision"]
    )
    assert m["promotion_statistics"]["registered_promoted_features"] == 1


def test_query_proof_crosses_actual_immutable_worker_whitelist():
 from lm_suti_assurance.symbolic.executor import Executor
 _,_,f=fitted();pool=Executor()
 try:
  value=pool.run({'action':'observer_verify','feature':f,'query_record':rec(list('SSPPSP')),'certificate':None})['data']
  assert value['status']=='CHECKED_INSTANCE' and len(value['certificate']['tree']['children'])==2
 finally:pool.close()
