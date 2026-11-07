"""Explicit finite relation/sequence catalog generated from train primitives only."""

from itertools import combinations, product
from ..core import digest
from .ir import grammar, complexity, limits, Budget, Bound
from .chart import parse
from .proof_checker import verify


def make(alphabet, rules, start="N0"):
    keys=sorted(rules)
    productions=[]
    for nt in keys:
        for rhs in sorted(rules[nt],key=digest):
            productions.append({"id":"p"+str(len(productions)),"lhs":nt,"rhs":rhs or [{"op":"EPS"}]})
    return grammar({"schema":"formal-grammar-ir/1","terminals":alphabet,"nonterminals":keys,"start":start,"productions":productions})


def catalog(records, bounds, work):
    alphabet=sorted({t for r in records for t in r["tokens"]})
    positive=[tuple(r["tokens"]) for r in records if r["accepted"]]
    positive_two={w for w in positive if len(w)==2}
    negative_two={tuple(r["tokens"]) for r in records if not r["accepted"] and len(r["tokens"])==2}
    term=lambda t:{"op":"TERM","value":t}
    ref=lambda nt="N0":{"op":"NT_REF","name":nt}
    centers=sorted({w[0] for w in positive if len(w)==1}|{w[1] for w in positive if len(w)==3})
    candidates={};reason=None;relations={}
    def add(rules):
        work.tick()
        try:g=make(alphabet,rules)
        except ValueError:return
        if len(g["productions"])<=bounds["max_rules"] and complexity(g)<=bounds["max_ast_nodes"] and len(g["nonterminals"])<=bounds["max_nt"]:
            if len(candidates)>=8192:raise Bound("CATALOG_SHAPE_BOUND")
            candidates[digest(g)]=g
    try:
        work.tick()
        if len(alphabet)>4:raise Bound("CATALOG_ALPHABET_BOUND")
        all_pairs=set(product(alphabet,repeat=2))
        # Short negatives eliminate pair bindings ONLY for EPS/literal-pair
        # bases. A center/non-nullable base need not admit its bare frame.
        normal=sorted(all_pairs-negative_two);required=sorted(positive_two)
        for count in range(max(1,len(required)),min(4,len(normal))+1):
            for extra in combinations(sorted(set(normal)-positive_two),count-len(required)):
                work.tick();relation=tuple(sorted(required+list(extra)));relations.setdefault(relation,set()).add('normal')
        if centers and not positive_two:
            for count in range(1,min(4,len(all_pairs))+1):
                for relation in combinations(sorted(all_pairs),count):
                    work.tick();relations.setdefault(relation,set()).add('center')
        for relation,kinds in sorted(relations.items()):
            for calls in [1,2]:
                for positions in combinations(range(2+calls),2):
                    rules=[]
                    for a,b in relation:
                        seq=[];atoms=iter([a,b])
                        for i in range(2+calls):seq.append(term(next(atoms)) if i in positions else ref())
                        rules.append(seq)
                    inside=[[{**v,"name":"N1"} if v["op"]=="NT_REF" else v for v in rr] for rr in rules]
                    if 'normal' in kinds:
                        add({"N0":[[],*rules]})
                        add({"N0":[*[[term(a),term(b)] for a,b in relation],*rules]})
                        add({"N0":inside,"N1":[[],*inside]})
                    if 'center' in kinds:
                        for center in centers:
                            add({"N0":[[term(center)],*rules]})
                            add({"N0":[*[[term(a),term(center),term(b)] for a,b in relation],*rules]})
                            add({"N0":inside,"N1":[[term(center)],*inside]})
        singles=sorted({w[0] for w in positive if len(w)==1})
        if singles:add({"N0":[*[[term(t)] for t in singles],[ref(),ref()]]})
        work.tick()
    except Bound as exc:reason=str(exc)
    ordered=sorted(candidates.values(),key=lambda g:(complexity(g),len(g["terminals"]),len(g["nonterminals"]),max(sum(v["op"]=="NT_REF" for v in p["rhs"]) for p in g["productions"]),digest(g)))
    return ordered,{"schema":"finite-primitive-catalog/1","constructors":["EPS","TERM","NT_REF","SEQ","ALT"],"alphabet":alphabet,"pair_relation_subsets_up_to":4,"pair_constraints_from_train":{"required_for_nullable_or_pair_base":sorted(positive_two),"short_negative_pruned_only_for_nullable_or_pair_base":sorted(negative_two)},"sequence_policy":"all two-terminal shuffles with1/2 NT_REF; EPS/literal-pair/observed-center bases; independent start; observed singleton+concat","ordering":"AST size,terminal types,NT count,recursive arity,canonical SHA within declared generated catalog","catalog_size":len(ordered),"all_catalog_ast_digests":[digest(g) for g in ordered],"catalog_generation_status":"UNKNOWN_BOUND:"+reason if reason else "CATALOG_GENERATED","unmaterialized_recipe":None if reason is None else "remaining pair-relation subsets/base/start/shuffles in declared generator; no full-CFG exhaustion","generation_limits":{"alphabet":4,"materialized_shapes":8192},"not_all_CFG":True}


def fit(records, constraints=None, bounds=None):
    bounds=bounds or limits();work=Budget(bounds)
    if not records or len(records)>256:raise ValueError("TRAIN_BOUND")
    if any(type(r.get("accepted")) is not bool for r in records):raise ValueError("TRAIN_LABEL_REQUIRED")
    labels={}
    for r in records:labels.setdefault(tuple(r["tokens"]),set()).add(r["accepted"])
    if any(len(v)>1 for v in labels.values()):return {"status":"CONTRADICTORY_TRAIN","candidates":[],"selected":None,"execution_permission":False}
    ordered,declared=catalog(records,bounds,work);candidates=[];considered=[];used=0;parsed=0;had_unknown=False;reason="NO_COMPATIBLE_IN_DECLARED_CATALOG"
    samples=sorted(records,key=lambda r:(len(r["tokens"]),r["accepted"],digest(r)))
    try:
        for g in ordered:
            work.tick()
            used+=1;counter=None;unknown=None
            # Sound constructor-level pruning: an unmentioned terminal can
            # never appear in a derived word. Retain the actual train witness.
            mentioned={s['value'] for p in g['productions'] for s in p['rhs'] if s['op']=='TERM'}
            missing=next((r for r in samples if r['accepted'] and set(r['tokens'])-mentioned),None)
            if missing:
                considered.append({'ast_sha256':digest(g),'ast':g,'status':'STRUCTURAL_TRAIN_PRUNED','counterexample':{'record_ref':digest(missing),'id':missing['id'],'expected':True,'observed':False,'reason':'TERMINAL_NOT_IN_PRODUCTIONS'}})
                continue
            short=[r for r in samples if len(r['tokens'])<=3]
            short_failure=None
            for r in short:
                work.tick();p=parse(g,r,bounds,certify=False)
                if p['decision'] is not None and p['decision']!=r['accepted']:
                    short_failure={'record_ref':digest(r),'id':r['id'],'expected':r['accepted'],'observed':p['decision'],'reason':'SHORT_TRAIN_COUNTEREXAMPLE'};break
            if short_failure:
                considered.append({'ast_sha256':digest(g),'ast':g,'status':'SHORT_TRAIN_PRUNED','counterexample':short_failure});continue
            if parsed>=bounds['max_candidates']:
                used-=1;raise Bound('CANDIDATE_BOUND')
            parsed+=1
            for r in samples:
                work.tick();p=parse(g,r,bounds,certify=False)
                if p["decision"] is None:unknown=p["status"];break
                if p["decision"]!=r["accepted"]:
                    counter={"record_ref":digest(r),"id":r["id"],"expected":r["accepted"],"observed":p["decision"]};break
            had_unknown=had_unknown or unknown is not None
            entry={"ast_sha256":digest(g),"ast":g,"status":"TRAIN_COMPATIBLE" if counter is None and unknown is None else unknown or "REJECTED_BY_TRAIN","counterexample":counter}
            considered.append(entry)
            if entry["status"]=="TRAIN_COMPATIBLE":
                # No producer scalar is an admission certificate.
                for r in samples:
                    work.tick();proof=parse(g,r,bounds);checked=verify(g,r,bounds,proof)
                    if checked["status"]!="CHECKED_INSTANCE" or checked["decision"]!=r["accepted"]:
                        entry["status"]="INDEPENDENT_CHECK_FAILED";had_unknown=True;break
                if entry["status"]=="TRAIN_COMPATIBLE":candidates.append({"candidate_id":digest(g),"ast":g,"origin":"TRAIN_PRIMITIVE_SEARCH","status":"TRAIN_COMPATIBLE","type_status":"TYPED","train_witnesses_checked":len(samples)})
        reason="UNKNOWN_BOUND:UNRESOLVED_CATALOG_OBLIGATIONS" if had_unknown or declared["catalog_generation_status"].startswith("UNKNOWN") else "CATALOG_CHECKED" if candidates else "NO_COMPATIBLE_IN_DECLARED_CATALOG"
    except Bound as exc:reason="UNKNOWN_BOUND:"+str(exc)
    declared['candidate_budget_unit']='Full-train candidates after explicit terminal-coverage and short-train counterexample pruning; all pruned ASTs retained, total bounded by CPU/steps'
    result={"schema":"formal-synthesis-model/1","kind":"CFG","status":"TRAIN_COMPATIBLE" if candidates else reason,"candidates":candidates,"selected":candidates[0]["candidate_id"] if candidates else None,"considered":considered,"catalog":declared,"search_status":reason,"parsed_candidates":parsed,"untried_ast_digests":[digest(g) for g in ordered[used:]],"bounds":bounds,"train_sha256":digest(records),"family_status":"UNDERDETERMINED","execution_permission":False,"UNIVERSAL_INVARIANT":False}
    result["hypothesis_sha256"]=digest(result);return result
