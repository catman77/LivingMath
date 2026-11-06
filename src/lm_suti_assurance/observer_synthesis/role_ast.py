"""Bounded nullable role programs: generic sequence partitions, not a named parser."""

from itertools import combinations
from ..core import digest, canonical, strict_json
from ..symbolic.state import apply
from .contexts import record_state


class RoleLimit(ValueError):
    pass


def domain(policy):
    return {
        "max_tokens": policy.get("role_max_tokens", policy.get("max_tokens", 8)),
        "max_cells": policy.get("role_max_cells", 91),
        "max_split_trials": policy.get("role_max_split_trials", 512),
        "max_depth": policy.get("max_recursion_steps", 8),
        "max_ast_nodes": policy.get("max_ast_nodes", 32),
        "max_ast_depth": policy.get("max_ast_depth", 8),
        "representation": "literal",
        "role_semantics": "LITERAL_ROLE_SENSITIVE",
        "renaming_contract": "ATOMS_AND_ROLES_TOGETHER",
        "NF_INVARIANT": False,
        "universal_invariant": False,
    }


def metrics(program):
    if not isinstance(program, dict) or set(program) != {
        "composition",
        "base",
        "roles",
        "sequence",
        "quantifier",
        "combine",
        "reconstruction",
    }:
        raise ValueError("INVALID_ROLE_PROGRAM")
    if (
        program["composition"] != "finite_role_branching"
        or program["base"] not in ["EPS", "NONE"]
        or program["quantifier"] != "FINITE_EXISTS"
        or program["combine"] != "BRANCH_AND"
        or program["reconstruction"] != "CONCAT"
    ):
        raise ValueError("INVALID_ROLE_PROGRAM")
    roles = program["roles"]
    seq = program["sequence"]
    if (
        not isinstance(roles, dict)
        or set(roles) != {"OPEN", "CLOSE"}
        or any(not isinstance(x, str) or not x or len(x) > 1024 for x in roles.values())
        or roles["OPEN"] == roles["CLOSE"]
    ):
        raise ValueError("INVALID_ROLE_BINDING")
    if not isinstance(seq, list) or not 2 <= len(seq) <= 4:
        raise ValueError("INVALID_RULE_ARITY")
    names = []
    branches = []
    for step in seq:
        if (
            isinstance(step, dict)
            and set(step) == {"op", "role"}
            and step["op"] == "ATOM_ROLE"
            and step["role"] in roles
        ):
            names.append(step["role"])
        elif (
            isinstance(step, dict)
            and set(step) == {"op", "branch"}
            and step["op"] == "RECURSE"
        ):
            branches.append(step["branch"])
        else:
            raise ValueError("INVALID_ROLE_INSTRUCTION")
    if (
        names != ["OPEN", "CLOSE"]
        or branches != ["b" + str(i) for i in range(len(branches))]
        or len(branches) > 2
    ):
        raise ValueError("NON_DECREASING_OR_INVALID_BRANCHES")
    return 7 + len(seq), 3


def catalog(records):
    alphabet = sorted({t for r in records for t in r["tokens"]})
    for a in alphabet:
        for b in alphabet:
            if a == b:
                continue
            for calls in range(3):
                for positions in combinations(range(calls + 2), 2):
                    seq = []
                    branch = 0
                    role = 0
                    for i in range(calls + 2):
                        if i in positions:
                            seq.append(
                                {"op": "ATOM_ROLE", "role": ["OPEN", "CLOSE"][role]}
                            )
                            role += 1
                        else:
                            seq.append({"op": "RECURSE", "branch": "b" + str(branch)})
                            branch += 1
                    for base in ["EPS", "NONE"]:
                        yield {
                            "composition": "finite_role_branching",
                            "base": base,
                            "roles": {"OPEN": a, "CLOSE": b},
                            "sequence": seq,
                            "quantifier": "FINITE_EXISTS",
                            "combine": "BRANCH_AND",
                            "reconstruction": "CONCAT",
                        }


def allocations(total, count):
    if total < 0:
        return []
    if count == 0:
        return [()] if total == 0 else []
    if count == 1:
        return [(total,)]
    return [(k, total - k) for k in range(total + 1)]


def execute(program, record, scope, *, certify=True, budget=None):
    nodes, depth = metrics(program)
    tokens = record["tokens"]
    n = len(tokens)
    calls = sum(s["op"] == "RECURSE" for s in program["sequence"])
    prefix = {
        "schema": "finite-role-certificate/1",
        "program_digest": digest(program),
        "record_ref": digest(record),
        "source_sha256": record["source"]["sha256"],
        "scope_digest": digest(scope),
        "input_state": strict_json(canonical(record_state(record).data())),
    }

    def unknown(reason):
        return None, {**prefix, "status": "UNKNOWN", "reason": reason}

    if n > scope["max_tokens"]:
        return unknown("OUT_OF_SCOPE")
    if nodes > scope["max_ast_nodes"] or depth > scope["max_ast_depth"]:
        return unknown("AST_BOUND")
    if (n + 1) * (n + 2) // 2 > scope["max_cells"]:
        return unknown("INTERVAL_CELL_BOUND")
    if calls and n // 2 > scope["max_depth"]:
        return unknown("RECURSION_DEPTH_BOUND")
    table = {}
    rows = []
    trials = 0
    for length in range(n + 1):
        for i in range(n - length + 1):
            if budget:
                budget.check()
            j = i + length
            chosen = [] if length == 0 and program["base"] == "EPS" else None
            for sizes in allocations(length - 2, calls):
                trials += 1
                if trials > scope["max_split_trials"]:
                    return unknown("SPLIT_TRIAL_BOUND")
                pos = i
                branch = 0
                valid = True
                for step in program["sequence"]:
                    if step["op"] == "ATOM_ROLE":
                        valid = valid and tokens[pos] == program["roles"][step["role"]]
                        pos += 1
                    else:
                        end = pos + sizes[branch]
                        valid = valid and table[(pos, end)]["value"]
                        pos = end
                        branch += 1
                if valid and chosen is None:
                    chosen = list(sizes)
            row = {"range": [i, j], "value": chosen is not None, "allocation": chosen}
            table[i, j] = row
            rows.append(row)
    if not table[0, n]["value"]:
        return False, (
            {
                **prefix,
                "status": "DECIDED",
                "decision": False,
                "cells": rows,
                "tree": None,
                "states": {},
                "work": {"cells": len(rows), "split_trials": trials},
            }
            if certify
            else None
        )
    states = {}

    def state_ref(s):
        ref = digest(s.data())
        states[ref] = strict_json(canonical(s.data()))
        return ref

    def step(state, name, args, other=None):
        if budget:
            budget.check()
        result, _ = apply(state, name, args, other)
        return result, {
            "operator": name,
            "args": args,
            "input_state_ref": state_ref(state),
            "other_state_ref": state_ref(other) if other is not None else None,
            "output_state_refs": [state_ref(x) for x in result],
            "input_word_hash": state.word_hash,
            "output_word_hashes": [x.word_hash for x in result],
        }

    def build(i, j, state, level):
        if level > scope["max_depth"]:
            raise RoleLimit("RECURSION_DEPTH_BOUND")
        row = table[i, j]
        node = {
            "range": [i, j],
            "tokens": list(state.tokens),
            "input_state_ref": state_ref(state),
            "kind": "EPS_BASE" if i == j else "RULE",
            "roles": [],
            "children": [],
            "trace": [],
            "allocation": row["allocation"],
            "measure": {"parent": j - i, "children": []},
            "reconstructed_tokens": list(state.tokens),
        }
        if i == j:
            return node
        remain = state
        parts = []
        pos = i
        branch = 0
        for ins in program["sequence"]:
            size = 1 if ins["op"] == "ATOM_ROLE" else row["allocation"][branch]
            (piece, tail), event = step(remain, "SPLIT", {"position": size})
            node["trace"].append(event)
            parts.append(piece)
            if ins["op"] == "ATOM_ROLE":
                node["roles"].append(
                    {
                        "role": ins["role"],
                        "position": pos,
                        "token": piece.tokens[0],
                        "state_ref": state_ref(piece),
                    }
                )
            else:
                if not size < j - i:
                    raise RoleLimit("NON_DECREASING_RECURSION")
                node["children"].append(build(pos, pos + size, piece, level + 1))
                node["measure"]["children"].append(size)
                branch += 1
            pos += size
            remain = tail
        reconstructed = parts[0]
        for piece in parts[1:]:
            (reconstructed,), event = step(reconstructed, "CONCAT", {}, piece)
            node["trace"].append(event)
        assert reconstructed.tokens == state.tokens and not remain.tokens
        node["reconstructed_tokens"] = list(reconstructed.tokens)
        return node

    if not certify:

        def height(i, j, level):
            if level > scope["max_depth"]:
                raise RoleLimit("RECURSION_DEPTH_BOUND")
            if i == j:
                return
            row = table[i, j]
            pos = i
            branch = 0
            for ins in program["sequence"]:
                if ins["op"] == "ATOM_ROLE":
                    pos += 1
                else:
                    size = row["allocation"][branch]
                    height(pos, pos + size, level + 1)
                    pos += size
                    branch += 1

        try:
            height(0, n, 0)
        except RoleLimit as e:
            return unknown(str(e))
        return True, None
    try:
        tree = build(0, n, record_state(record), 0)
    except RoleLimit as e:
        return unknown(str(e))
    return True, {
        **prefix,
        "status": "DECIDED",
        "decision": True,
        "cells": rows,
        "tree": tree,
        "states": states,
        "work": {"cells": len(rows), "split_trials": trials},
    }
