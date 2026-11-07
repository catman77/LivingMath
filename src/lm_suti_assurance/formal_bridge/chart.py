"""Least fixed-point chart and finite packed forest, with explicit cycle limits."""

from itertools import product
from ..core import digest
from .ir import grammar, complexity, header, Budget, Bound


def parse(ast, record, bounds, budget=None, certify=True):
    grammar(ast)
    out = {**header(ast, record, bounds), "start_symbol": ast["start"]}
    n = len(record["tokens"])
    work = budget or Budget(bounds)

    def unknown(status, reason):
        return {**out, "status": status, "decision": None, "reason": reason}

    if n > bounds["max_tokens"] or complexity(ast) > bounds["max_ast_nodes"] or len(ast["productions"]) > bounds["max_rules"] or len(ast["nonterminals"]) > bounds["max_nt"] or any(len(p["rhs"]) > bounds["max_rhs"] for p in ast["productions"]):
        return unknown("UNKNOWN_BOUND", "DOMAIN_BOUND")
    chart = set()
    families = {}
    edge_count = 0

    def matches(rhs, k, pos, end, children):
        work.tick()
        if k == len(rhs):
            if pos == end:
                yield children
            return
        symbol = rhs[k]
        if symbol["op"] == "EPS":
            yield from matches(rhs, k+1, pos, end, children)
        elif symbol["op"] == "TERM":
            if pos < end and record["tokens"][pos] == symbol["value"]:
                child = {"terminal": symbol["value"], "index": pos, "source_span": out["token_spans"][pos]}
                yield from matches(rhs, k+1, pos+1, end, children+[child])
        else:
            for stop in range(pos, end+1):
                key = (symbol["name"], pos, stop)
                if key in chart:
                    yield from matches(rhs, k+1, stop, end, children+[{"node": list(key)}])

    try:
        # At each length, same-span nullable/unit/left-recursive dependencies
        # reach their finite least fixed point before the next length.
        for length in range(n+1):
            change = True
            while change:
                change = False
                for i in range(n-length+1):
                    for rule in ast["productions"]:
                        key = (rule["lhs"], i, i+length)
                        for children in matches(rule["rhs"], 0, i, i+length, []):
                            if certify:
                                family = {"production_id": rule["id"], "children": children}
                                variants = families.setdefault(key, {})
                                ident = digest(family)
                                if ident not in variants:
                                    variants[ident] = family
                                    edge_count += 1
                                    if edge_count > bounds["max_forest_edges"]:
                                        raise Bound("FOREST_EDGE_BOUND")
                            if key not in chart:
                                chart.add(key)
                                change = True
                            if not certify:
                                break
        root = (ast["start"], 0, n)
        if not certify:
            return {**out, "status": "ACCEPT_WITH_WITNESS" if root in chart else "REJECT_COMPLETE", "decision": root in chart}
        forest = [{"node": list(k), "families": [v[h] for h in sorted(v)]} for k,v in sorted(families.items())]
        if root not in chart:
            return {**out, "status": "REJECT_COMPLETE", "decision": False,
                    "forest": forest, "trees": [], "forest_complete": True}
        active = set()
        cyclic = False
        truncated = False

        def trees(key):
            nonlocal cyclic, truncated
            work.tick()
            if key in active:
                cyclic = True
                return []
            active.add(key)
            answer = []
            for ident, f in sorted(families[key].items()):
                groups = [trees(tuple(c["node"])) if "node" in c else [c] for c in f["children"]]
                for children in product(*groups):
                    if len(answer) >= bounds["max_trees"]:
                        truncated = True
                        break
                    answer.append({"node": list(key), "production_id": f["production_id"], "children": list(children)})
            active.remove(key)
            return answer

        expanded = trees(root)
        if cyclic:
            return unknown("UNKNOWN_CYCLE", "CYCLIC_DERIVATION_FOREST")
        return {**out, "status": "ACCEPT_WITH_WITNESS", "decision": True,
                "forest": forest, "trees": expanded,
                "forest_complete": True, "expanded_trees_complete": not truncated}
    except Bound as exc:
        return unknown("UNKNOWN_BOUND", str(exc))
