"""Independent source, least-fixed-point and proof checks; imports no producer/search."""

import hashlib
import re
from itertools import product
from ..core import digest, canonical
from .ir import grammar, dfa, complexity, Budget, Bound


def verify(ast, record, bounds, proof):
    def reject(reason):
        return {"status": "REJECTED_PROOF", "reason": reason, "decision": None, "execution_permission": False}

    def unknown(reason):
        return {"status": reason, "decision": None, "execution_permission": False}

    try:
        if not isinstance(proof, dict):
            return reject("NOT_AN_OBJECT")
        text = record["source"]["text"]
        raw = text.encode("utf8")
        spans = [[len(text[:m.start()].encode()), len(text[:m.end()].encode())] for m in re.finditer(r"\S+", text)]
        if hashlib.sha256(raw).hexdigest() != record["source"]["sha256"] or [raw[a:b].decode() for a,b in spans] != record["tokens"] or not record["source"]["rights"].strip() or not record["source"]["edition"].strip():
            return reject("SOURCE_LINEAGE")
        binding = {"schema": "formal-membership-proof/1", "grammar_sha256": digest(ast), "record_ref": digest(record), "source_sha256": hashlib.sha256(raw).hexdigest(), "tokens": record["tokens"], "token_spans": spans, "bounds_sha256": digest(bounds)}
        if any(canonical(proof.get(k)) != canonical(v) for k,v in binding.items()):
            return reject("BINDING_OR_SPAN")
        n = len(record["tokens"])
        if n > bounds["max_tokens"]:
            return unknown("UNKNOWN_BOUND") if proof.get("status") == "UNKNOWN_BOUND" and proof.get("decision") is None else reject("DOMAIN_BOUND")
        work = Budget(bounds)
        if ast.get("schema") == "formal-dfa-ir/1":
            dfa(ast)
            if len(ast["states"]) > bounds["max_states"]:
                return unknown("UNKNOWN_BOUND")
            state = ast["start"]
            delta = {(e["from"],e["token"]):e["to"] for e in ast["delta"]}
            expected = []
            for i, token in enumerate(record["tokens"]):
                work.tick()
                if (state,token) not in delta:
                    return unknown("UNKNOWN_BOUND") if proof.get("status") == "UNKNOWN_BOUND" and proof.get("decision") is None else reject("ALPHABET_BOUND")
                to = delta[state,token]
                expected.append({"from": state, "token": token, "index": i, "source_span": spans[i], "target": to})
                state = to
            decision = state in ast["accepting"]
            expected_proof = {**binding, "start_state": ast["start"], "status": "ACCEPT_WITH_WITNESS" if decision else "REJECT_COMPLETE", "decision": decision, "trace": expected, "final_state": state}
            if canonical(proof) != canonical(expected_proof):
                return reject("DFA_TRANSITION_TRACE")
        else:
            grammar(ast)
            if proof.get("start_symbol") != ast["start"]:
                return reject("START_SYMBOL")
            if complexity(ast) > bounds["max_ast_nodes"] or len(ast["productions"]) > bounds["max_rules"] or len(ast["nonterminals"]) > bounds["max_nt"] or any(len(p["rhs"]) > bounds["max_rhs"] for p in ast["productions"]):
                return unknown("UNKNOWN_BOUND") if proof.get("status") == "UNKNOWN_BOUND" and proof.get("decision") is None else reject("AST_BOUND")
            # Different traversal from producer: global monotone saturation,
            # then enumerate every complete rule allocation from the final set.
            known = set()
            def allocations(rhs, i, j):
                frontier = [(i, [])]
                for symbol in rhs:
                    following = []
                    for at, children in frontier:
                        work.tick()
                        if symbol["op"] == "EPS":
                            following.append((at,children))
                        elif symbol["op"] == "TERM":
                            if at < j and record["tokens"][at] == symbol["value"]:
                                following.append((at+1,children+[{"terminal":symbol["value"],"index":at,"source_span":spans[at]}]))
                        else:
                            for end in range(at,j+1):
                                if (symbol["name"],at,end) in known:
                                    following.append((end,children+[{"node":[symbol["name"],at,end]}]))
                    frontier = following
                return [children for at,children in frontier if at==j]
            changed = True
            while changed:
                changed = False
                for rule in reversed(ast["productions"]):
                    for end in range(n+1):
                        for begin in range(end+1):
                            key=(rule["lhs"],begin,end)
                            if key not in known and allocations(rule["rhs"],begin,end):
                                known.add(key);changed=True
            families = {}
            for name,begin,end in sorted(known):
                variants = {}
                for rule in ast["productions"]:
                    if rule["lhs"] == name:
                        for children in allocations(rule["rhs"],begin,end):
                            f={"production_id":rule["id"],"children":children};variants[digest(f)]=f
                families[name,begin,end]=[variants[h] for h in sorted(variants)]
            if sum(len(v) for v in families.values()) > bounds["max_forest_edges"]:
                return unknown("UNKNOWN_BOUND") if proof.get("status")=="UNKNOWN_BOUND" else reject("FOREST_BOUND")
            expected_forest=[{"node":list(k),"families":v} for k,v in sorted(families.items())]
            root=(ast["start"],0,n)
            graph={k:[tuple(c["node"]) for f in fs for c in f["children"] if "node" in c] for k,fs in families.items()}
            active=set();done=set()
            def cycle(k):
                if k in active:return True
                if k in done:return False
                active.add(k)
                if any(cycle(c) for c in graph.get(k,[])):return True
                active.remove(k);done.add(k);return False
            if root in known and cycle(root):
                return unknown("UNKNOWN_CYCLE") if proof.get("status")=="UNKNOWN_CYCLE" and proof.get("decision") is None else reject("CYCLIC_FOREST")
            decision=root in known
            if proof.get("status") != ("ACCEPT_WITH_WITNESS" if decision else "REJECT_COMPLETE") or type(proof.get("decision")) is not bool or proof["decision"] != decision or proof.get("forest_complete") is not True or canonical(proof.get("forest")) != canonical(expected_forest):
                return reject("INCOMPLETE_OR_FORGED_FOREST")
            trees=proof.get("trees")
            if not isinstance(trees,list) or len(trees)>bounds["max_trees"] or (not decision and trees) or (decision and not trees):return reject("MISSING_OR_INVALID_TREES")
            def check_tree(t,k):
                work.tick()
                if not isinstance(t,dict) or set(t)!={"node","production_id","children"} or canonical(t["node"])!=canonical(list(k)) or not isinstance(t["children"],list):return False
                refs=[]
                for child in t["children"]:
                    if isinstance(child,dict) and "production_id" in child:
                        ck=tuple(child.get("node",[]))
                        if ck not in families or not check_tree(child,ck):return False
                        refs.append({"node":list(ck)})
                    else:refs.append(child)
                return canonical({"production_id":t["production_id"],"children":refs}) in {canonical(f) for f in families[k]}
            if any(not check_tree(t,root) for t in trees) or len({digest(t) for t in trees})!=len(trees):return reject("INVALID_EXPANDED_TREE")
            counts={}
            def count(k):
                if k in counts:return counts[k]
                total=0
                for f in families[k]:
                    ways=1
                    for c in f["children"]:
                        if "node" in c:ways*=count(tuple(c["node"]))
                    total+=ways
                counts[k]=min(total,bounds["max_trees"]+1);return counts[k]
            if decision and (type(proof.get("expanded_trees_complete")) is not bool or proof["expanded_trees_complete"] != (count(root)<=bounds["max_trees"]) or len(trees)!=min(count(root),bounds["max_trees"])):return reject("TREE_COVERAGE")
        return {"status":"CHECKED_INSTANCE","decision":decision,"proof_sha256":digest(proof),"checker":"formal-independent-checker/1","execution_permission":False,"UNIVERSAL_INVARIANT":False}
    except Bound:
        return unknown("UNKNOWN_BOUND")
    except (ValueError,TypeError,KeyError,IndexError,RecursionError):
        return reject("INVALID_PROOF_OR_IR")
