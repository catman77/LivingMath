"""Typed concrete checks using the supplied exact rational matrix operations."""

from fractions import Fraction
from .contracts import fail


def evaluate(proposal: dict, ops) -> dict:
    family = proposal["family"]
    if family not in ("observation_invariant", "control_invariant", "cyclic_order"):
        return {
            "status": "UNSUPPORTED_MODEL",
            "family": family,
            "reason": "Only three rational matrix families are registered",
            "execution_permission": False,
        }
    allowed = {
        "observation_invariant": {
            "invariant_identity",
            "hidden_state_change",
            "countermodel",
        },
        "control_invariant": {
            "invariant_identity",
            "partial_improvement",
            "countermodel",
        },
        "cyclic_order": {"conjugacy", "different_action", "countermodel"},
    }[family]
    if not set(proposal["obligations"]) <= allowed:
        fail(
            "INVALID_INPUT",
            "/proposal/obligations",
            "Obligation does not belong to family",
        )

    def matrix(rows):
        if (
            not isinstance(rows, list)
            or not 1 <= len(rows) <= 8
            or not isinstance(rows[0], list)
            or not 1 <= len(rows[0]) <= 8
            or any(not isinstance(r, list) or len(r) != len(rows[0]) for r in rows)
        ):
            fail(
                "INVALID_INPUT",
                "/proposal/matrices",
                "Rectangular 1..8 matrix required",
            )
        result = []
        import re

        for row in rows:
            values = []
            for v in row:
                if type(v) is not int and (
                    not isinstance(v, str)
                    or len(v) > 158
                    or not re.fullmatch(r"-?(0|[1-9][0-9]*)(/[1-9][0-9]*)?", v)
                ):
                    fail(
                        "INVALID_INPUT",
                        "/proposal/matrices",
                        "Exact bounded rational required",
                    )
                try:
                    f = Fraction(v)
                except (ValueError, ZeroDivisionError):
                    fail("INVALID_INPUT", "/proposal/matrices", "Invalid denominator")
                if f.numerator.bit_length() > 256 or f.denominator.bit_length() > 256:
                    fail(
                        "INVALID_INPUT",
                        "/proposal/matrices",
                        "Rational exceeds256 bits",
                    )
                values.append(f)
            result.append(values)
        return ops.mat(result)

    m = {k: matrix(v) for k, v in proposal["matrices"].items()}
    checks = []
    witness = {}

    def obligation(name, condition, **values):
        checks.append(
            {
                "obligation": name,
                "pass": bool(condition),
                "witness": {k: ops.serial(v) for k, v in values.items()},
            }
        )

    def zero(a):
        return all(v == 0 for row in a for v in row)

    try:
        if family == "observation_invariant":
            if set(m) != {"A", "C", "x"}:
                fail("INVALID_INPUT", "/proposal/matrices", "A,C,x required")
            A, C, x = (m[k] for k in ("A", "C", "x"))
            n = len(A)
            if len(A[0]) != n or len(x) != n or len(x[0]) != 1 or len(C[0]) != n:
                fail("INVALID_INPUT", "/proposal/matrices", "Incompatible shapes")
            CA = ops.mul(C, A)
            nxt = ops.mul(A, x)
            obligation("CA=C", CA == C, CA=CA, C=C)
            if "hidden_state_change" in proposal["obligations"]:
                obligation("Ax!=x", nxt != x, Ax=nxt, x=x)
                obligation(
                    "CAx=Cx",
                    ops.mul(C, nxt) == ops.mul(C, x),
                    CAx=ops.mul(C, nxt),
                    Cx=ops.mul(C, x),
                )
        elif family == "control_invariant":
            if set(m) != {"A", "B", "C", "w", "x", "u"}:
                fail("INVALID_INPUT", "/proposal/matrices", "A,B,C,w,x,u required")
            A, B, C, w, x, u = (m[k] for k in ("A", "B", "C", "w", "x", "u"))
            n = len(A)
            if (
                len(A[0]) != n
                or len(B) != n
                or len(C[0]) != n
                or len(w) != 1
                or len(w[0]) != n
                or len(x) != n
                or len(x[0]) != 1
                or len(u) != len(B[0])
                or len(u[0]) != 1
            ):
                fail("INVALID_INPUT", "/proposal/matrices", "Incompatible shapes")
            wa = ops.mul(w, A)
            wb = ops.mul(w, B)
            nxt = ops.add(ops.mul(A, x), ops.mul(B, u))
            obligation("wA=w", wa == w, wA=wa, w=w)
            obligation("wB=0", zero(wb), wB=wb)
            if "partial_improvement" in proposal["obligations"]:
                obligation(
                    "partial_improvement",
                    not zero(ops.mul(C, x))
                    and zero(ops.mul(C, nxt))
                    and not zero(ops.mul(w, x)),
                    Cx=ops.mul(C, x),
                    Cx_next=ops.mul(C, nxt),
                    wx=ops.mul(w, x),
                )
        else:
            if set(m) != {"U", "L", "P", "x"}:
                fail("INVALID_INPUT", "/proposal/matrices", "U,L,P,x required")
            U, L, P, x = (m[k] for k in ("U", "L", "P", "x"))
            if any(len(a) != 2 or len(a[0]) != 2 for a in (U, L, P)):
                return {
                    "status": "UNSUPPORTED_MODEL",
                    "family": family,
                    "reason": "cyclic_order currently2x2 only",
                    "execution_permission": False,
                }
            if len(x) != 2 or len(x[0]) != 1:
                fail("INVALID_INPUT", "/proposal/matrices/x", "2x1 vector required")
            first = ops.compose([U, L, P])
            last = ops.compose([P, U, L])
            invertible = ops.det2(P) != 0
            obligation("P invertible", invertible, P=P)
            if invertible:
                obligation(
                    "M1=P^-1 M0 P",
                    ops.mul(ops.mul(ops.inverse2(P), first), P) == last,
                    M0=first,
                    M1=last,
                )
            if "different_action" in proposal["obligations"]:
                obligation(
                    "M0x!=M1x",
                    ops.mul(first, x) != ops.mul(last, x),
                    M0x=ops.mul(first, x),
                    M1x=ops.mul(last, x),
                )
        if (
            "countermodel" in proposal["obligations"]
            and family == "observation_invariant"
        ):
            counter = proposal.get("countermodel")
            if (
                not isinstance(counter, dict)
                or not counter
                or set(counter) - {"A", "C", "x"}
            ):
                fail(
                    "INVALID_INPUT",
                    "/proposal/countermodel",
                    "Explicit A/C/x overrides required",
                )
            cm = {**m, **{k: matrix(v) for k, v in counter.items()}}
            next_state = ops.mul(cm["A"], cm["x"])
            obligation(
                "countermodel_to_full_state_identity",
                ops.mul(cm["C"], cm["A"]) == cm["C"]
                and next_state != cm["x"]
                and ops.mul(cm["C"], next_state) == ops.mul(cm["C"], cm["x"]),
                A=cm["A"],
                C=cm["C"],
                x=cm["x"],
                Ax=next_state,
            )
        if (
            "countermodel" in proposal["obligations"]
            and family != "observation_invariant"
        ):
            c = proposal.get("countermodel")
            if not isinstance(c, dict) or not c or set(c) - set(m):
                fail(
                    "INVALID_INPUT",
                    "/proposal/countermodel",
                    "Explicit matrix overrides required",
                )
            cm = {**m, **{k: matrix(v) for k, v in c.items()}}
            if family == "control_invariant":
                rescued = ops.add(ops.mul(cm["A"], cm["x"]), ops.mul(cm["B"], cm["u"]))
                obligation(
                    "countermodel_removes_control_premise",
                    not zero(ops.mul(cm["w"], cm["B"])) and zero(rescued),
                    wB=ops.mul(cm["w"], cm["B"]),
                    final=rescued,
                )
            else:
                a = ops.compose([cm["U"], cm["L"], cm["P"]])
                b = ops.compose([cm["P"], cm["U"], cm["L"]])
                obligation(
                    "countermodel_different_action",
                    ops.mul(a, cm["x"]) != ops.mul(b, cm["x"]),
                    M0x=ops.mul(a, cm["x"]),
                    M1x=ops.mul(b, cm["x"]),
                )
    except (ValueError, IndexError, KeyError, ZeroDivisionError) as e:
        fail("INVALID_INPUT", "/proposal/matrices", str(e))
    return {
        "status": "CHECKED_INSTANCE" if all(x["pass"] for x in checks) else "REJECTED",
        "family": family,
        "obligations": checks,
        "source_binding": "REGISTERED_READING_AND_FRAME_BYTES",
        "translation_fidelity": "LLM_PROPOSED_NOT_INDEPENDENTLY_CERTIFIED",
        "physical_validity": "NOT_TESTED_NOT_CLAIMED",
        "interpretation_status": "INTERPRETATION",
        "execution_permission": False,
    }
