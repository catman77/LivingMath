"""Exact rational checks of three explicit LLM-proposed transfer models.

The mathematical statements have general proofs in TRANSFER_RU.md. This code
checks their premises, concrete instances and counterexamples; it does not
infer a formula from Russian prose or certify authorial intent.
"""
from fractions import Fraction as F
from pathlib import Path
import hashlib
import json
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "llm_white_star_formal"))
from formal_core import load_case, locate, check_excerpt


def mat(rows):
    if not rows or not rows[0] or any(len(row) != len(rows[0]) for row in rows):
        raise ValueError("nonempty rectangular matrix required")
    return tuple(tuple(F(v) for v in row) for row in rows)


def mul(a, b):
    if len(a[0]) != len(b):
        raise ValueError("incompatible matrix dimensions")
    return tuple(tuple(sum((a[i][k] * b[k][j] for k in range(len(b))), F(0))
                       for j in range(len(b[0]))) for i in range(len(a)))


def add(a, b):
    if len(a) != len(b) or len(a[0]) != len(b[0]):
        raise ValueError("matrix shapes differ")
    return tuple(tuple(x + y for x, y in zip(ra, rb)) for ra, rb in zip(a, b))


def neg(a):
    return tuple(tuple(-v for v in row) for row in a)


def identity(n):
    return tuple(tuple(F(i == j) for j in range(n)) for i in range(n))


def det2(a):
    if (len(a), len(a[0])) != (2, 2):
        raise ValueError("2x2 matrix required")
    return a[0][0] * a[1][1] - a[0][1] * a[1][0]


def inverse2(a):
    d = det2(a)
    if d == 0:
        raise ValueError("noninvertible operator")
    return ((a[1][1] / d, -a[0][1] / d), (-a[1][0] / d, a[0][0] / d))


def compose(operators):
    """Input order is application order: [U,L,P] -> P L U."""
    result = identity(len(operators[0]))
    for operator in operators:
        result = mul(operator, result)
    return result


def serial(a):
    return [[int(x) if x.denominator == 1 else str(x) for x in row] for row in a]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def proposed_transfers(data, prose):
    by_frame = {r["frame_id"]: r for r in prose["readings"]}
    def source(frame, quote):
        r = by_frame[frame]
        return dict(frame_id=frame, reading_title=r["title"], reading_sha256=hashlib.sha256(r["text"].encode()).hexdigest(),
                    excerpt=locate(r["text"], quote), poem_sha256=data["source"]["sha256"],
                    source_status="LLM_INTERPRETATION_NOT_ENTAILED_WORLD_FACT")
    return dict(schema="white-star-formal-transfer/1", target="rational linear systems",
                translation_status="LLM_PROPOSED_PARTIAL_MODELS; formal premises and examples checked separately",
                units=[
        dict(id="M1", source=source("F05", "В таком прочтении повторяется маленькая удостоверенная картинка, а за её границей остаётся неопределённость: мы ещё не знаем, что там успело измениться."),
             claim="Неизменная наблюдаемая картинка допускает изменение полного состояния.",
             roles={"освещённая картинка": "y=Cx", "полная сцена": "x", "изменение сцены": "x_next=A x", "неразличимое": "ker(C)"},
             added_assumptions=["rational vector state", "linear time-invariant observation and dynamics", "same C used before and after"],
             not_transferred=["pharmacy dissolving in medication", "night as a literary image", "any claim about physical light"],
             obligation="C A=C and exists x: A x != x",
             theorem="C A=C iff image(A-I) is a subset of kernel(C); then C A^t=C for all integer t>=0. If kernel(C)={0}, C A=C implies A=I.",
             false_strengthening="C A=C implies A=I without requiring C to be injective.",
             model=dict(A=[[1,0],[0,2]], C=[[1,0]], x=[[1],[1]])),
        dict(id="M2", source=source("F03", "Аптека лечит отдельные боли; тусклый свет делает видимой общую беспомощность."),
             claim="Доступное воздействие устраняет одну компоненту, сохраняя недоступную ему компоненту.",
             roles={"аптека / воздействие": "control u through B", "отдельная боль": "C x", "неустранённое ограничение": "w x", "повторные обращения": "arbitrary finite control sequence"},
             added_assumptions=["x_next=A x+B u", "w A=w", "w B=0", "w x_initial !=0"],
             not_transferred=["medical effectiveness", "life as diagnosis", "pharmacological claims"],
             obligation="exists u eliminating C x_next while nonzero w x is invariant under every control sequence",
             theorem="If w A=w and w B=0, then w x_t=w x_0 for every t and every control sequence. If w x_0!=0, x_t=0 is unreachable.",
             false_strengthening="Every intervention is powerless, including when it can act on the previously invariant component.",
             model=dict(A=[[1,0],[0,1]], B=[[1],[0]], C=[[1,0]], w=[[0,1]], x=[[3],[1]], u=[[-3]]),
             countermodel=dict(B=[[1,0],[0,1]], u=[[-3],[-1]])),
        dict(id="M3", source=source("F06", "знакомые предметы ещё на месте, но взгляд уже собирает их в другом порядке."),
             claim="Перестановка прежних элементов может сохранить часть инвариантов и изменить результат действия.",
             roles={"улица": "U", "фонарь": "L", "аптека": "P", "порядок перечисления": "order of application", "новая сборка": "different composite operator"},
             added_assumptions=["common triple only, not the whole poem", "objects represented as operators", "P invertible", "chronological order composes right-to-left"],
             not_transferred=["night and additional canal imagery", "any evidence that objects literally act as these matrices"],
             source_order_scope="Общая тройка: улица-фонарь-аптека -> аптека-улица-фонарь; полные перечисления не считаются тождественными.",
             first_order=["street","lamp","pharmacy"], last_order=["pharmacy","street","lamp"],
             obligation="same operator multiset; changed order; P^-1 M_first P=M_last; M_first x != M_last x in this model",
             theorem="For M_first=P L U and M_last=L U P with invertible P, M_last=P^-1 M_first P. Equal characteristic polynomials do not require equal operators or equal outputs on a fixed x.",
             false_strengthening="The same multiset of elements guarantees the same composite action.",
             model=dict(U=[[1,1],[0,1]], L=[[1,0],[1,1]], P=[[2,0],[0,1]], x=[[1],[0]])),
    ])


def verify_transfers(proposal, data, prose):
    by_frame = {r["frame_id"]: r for r in prose["readings"]}
    require([u["id"] for u in proposal["units"]] == ["M1", "M2", "M3"], "fixed three-case protocol changed")
    checks = []
    for unit in proposal["units"]:
        source = unit["source"]
        reading = by_frame[source["frame_id"]]
        require(source["reading_sha256"] == hashlib.sha256(reading["text"].encode()).hexdigest(), "wrong source reading hash")
        require(source["poem_sha256"] == data["source"]["sha256"], "wrong poem")
        require(source["source_status"] == "LLM_INTERPRETATION_NOT_ENTAILED_WORLD_FACT", "interpretation promoted to world fact")
        check_excerpt(reading["text"], source["excerpt"])
        m = {key: mat(value) for key, value in unit["model"].items()}
        if unit["id"] == "M1":
            A,C,x=m["A"],m["C"],m["x"]
            changed=mul(A,x)
            require(mul(C,A)==C, "M1 observation is not invariant")
            require(changed!=x, "M1 has no hidden state change")
            require(mul(C,changed)==mul(C,x), "M1 observed outputs differ")
            difference=add(A,neg(identity(len(A))))
            require(mul(C,difference)==tuple(tuple(F(0) for _ in row) for row in C), "M1 kernel condition failed")
            checks.append(dict(id="M1", premises="PASS", relational_obligations="PASS", counterexample_to_strengthening="PASS",
                               x=serial(x), x_next=serial(changed), observed=serial(mul(C,x)),
                               A_minus_I=serial(difference),
                               general_claim_status="ALGEBRAIC_PROOF_IN_TRANSFER_RU; this code checks the concrete instance"))
        elif unit["id"] == "M2":
            A,B,C,w,x,u=(m[k] for k in ("A","B","C","w","x","u"))
            require(mul(w,A)==w, "M2 dynamics does not preserve w")
            require(all(v==0 for row in mul(w,B) for v in row), "M2 control acts on the claimed invariant")
            invariant=mul(w,x)
            require(any(v!=0 for row in invariant for v in row), "M2 invariant is zero")
            nxt=add(mul(A,x),mul(B,u))
            require(any(v!=0 for row in mul(C,x) for v in row) and all(v==0 for row in mul(C,nxt) for v in row), "M2 no demonstrated partial improvement")
            require(mul(w,nxt)==invariant, "M2 invariant changed")
            counter={k:mat(v) for k,v in unit["countermodel"].items()}
            rescued=add(mul(A,x),mul(counter["B"],counter["u"]))
            require(all(v==0 for row in rescued for v in row), "M2 countermodel does not reach zero")
            require(any(v!=0 for row in mul(w,counter["B"]) for v in row), "M2 countermodel did not remove the critical premise")
            checks.append(dict(id="M2", premises="PASS", relational_obligations="PASS", counterexample_to_strengthening="PASS",
                               x_initial=serial(x), x_after_control=serial(nxt), invariant=serial(invariant),
                               countermodel_final_state=serial(rescued),
                               general_claim_status="PROVED_BY_ONE_STEP_IDENTITY_AND_INDUCTION_IN_TRANSFER_RU"))
        else:
            operators={"street":m["U"],"lamp":m["L"],"pharmacy":m["P"]}
            require(unit["first_order"]==["street","lamp","pharmacy"] and unit["last_order"]==["pharmacy","street","lamp"], "M3 source order altered")
            # Verify the common triple against the addressed source occurrences.
            concepts={c["id"]:c for c in data["concepts"]}
            def word_order(line):
                entries=[(e["byte_start"],key) for key in operators for e in concepts[key]["evidence"] if e["line"]==line]
                return [key for _,key in sorted(entries)]
            require(word_order(1)==unit["first_order"] and word_order(8)==unit["last_order"], "M3 common triple not in source order")
            first=compose([operators[k] for k in unit["first_order"]])
            last=compose([operators[k] for k in unit["last_order"]])
            conjugate=mul(mul(inverse2(m["P"]),first),m["P"])
            require(conjugate==last, "M3 conjugacy failed")
            a,b=mul(first,m["x"]),mul(last,m["x"])
            require(a!=b, "M3 no demonstrated change of action")
            poly_first=[F(1),-(first[0][0]+first[1][1]),det2(first)]
            poly_last=[F(1),-(last[0][0]+last[1][1]),det2(last)]
            require(poly_first==poly_last, "M3 characteristic polynomials differ")
            checks.append(dict(id="M3", premises="PASS", relational_obligations="PASS", counterexample_to_strengthening="PASS",
                               first=serial(first), last=serial(last), first_output=serial(a), last_output=serial(b),
                               characteristic_polynomial=[int(v) if v.denominator == 1 else str(v) for v in poly_first],
                               general_claim_status="PROVED_BY_ASSOCIATIVITY_AND_INVERTIBILITY_IN_TRANSFER_RU"))
    return dict(units=checks, all_concrete_obligations_pass=True,
                translation_fidelity="LLM_PROPOSED_MAPPING_NOT_INDEPENDENTLY_CERTIFIED",
                physical_validity="NOT_TESTED_NOT_CLAIMED", mathematical_novelty="NOT_CLAIMED")


if __name__ == "__main__":
    data, trace, frames, prose = load_case()
    proposal = proposed_transfers(data, prose)
    (HERE / "transfer_proposal.json").write_text(json.dumps(proposal, ensure_ascii=False, indent=2) + "\n")
    print("Three partial transfer proposals recorded; validation is a separate step.")
