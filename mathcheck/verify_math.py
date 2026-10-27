"""Answer verification.

For each question three things must agree:
  1. check:        code that computes the answer from the question's conditions only and sets `result`
  2. expected:     the intended answer (number, sympy-readable expression, or a list)
  3. final_answer: the answer string actually printed on the solutions sheet

Pass = check result == expected, and the printed final answer shows the expected value.
"""
from __future__ import annotations

import json
import re
from math import floor, log10

import sympy as sp

from .sandbox import run_check, safe_parse_expr
from .spec import Report


def _to_sympy(v):
    if isinstance(v, (list, tuple, set)):
        return [_to_sympy(i) for i in v]
    if isinstance(v, bool):
        return sp.true if v else sp.false
    if isinstance(v, int):
        return sp.Integer(v)
    if isinstance(v, float):
        return sp.Float(v)
    return safe_parse_expr(v)


def _equal(a, b, tol: float | None) -> bool:
    if isinstance(a, list) or isinstance(b, list):
        if not (isinstance(a, list) and isinstance(b, list)) or len(a) != len(b):
            return False
        bs = list(b)
        for item in a:
            hit = next((j for j, other in enumerate(bs) if _equal(item, other, tol)), None)
            if hit is None:
                return False
            bs.pop(hit)
        return True
    try:
        if tol is None and sp.simplify(sp.nsimplify(a) - sp.nsimplify(b)) == 0:
            return True
        fa, fb = complex(sp.N(a)), complex(sp.N(b))
        limit = tol if tol is not None else 1e-9 * max(1.0, abs(fb))
        return abs(fa - fb) <= limit
    except Exception:
        return str(a) == str(b)


def _round_sf(v: float, sf: int) -> float:
    if v == 0:
        return 0.0
    return round(v, sf - 1 - floor(log10(abs(v))))


def _numbers_in(text: str) -> list[float]:
    cleaned = text.replace("{,}", "").replace(",", "")
    # '-' is a sign only when not preceded by a letter, digit or closing bracket (the 4 in x-4 is positive)
    return [float(m) for m in re.findall(r"(?:(?<![\w)\]}])-)?\d+(?:\.\d+)?", cleaned)]


def verify_question(q: dict, timeout: int = 20) -> Report:
    rep = Report()
    qid = f"Q{q.get('id', '?')}"
    tol = q.get("tolerance")
    sf = q.get("sf")

    computed, err = run_check(q.get("check", ""), timeout=timeout)
    if err:
        rep.add("error", qid, err[0], **err[1])
        return rep
    try:
        expected = _to_sympy(q.get("expected"))
    except Exception as e:  # noqa: BLE001
        rep.add("error", qid, "math.bad_expected", detail=e)
        return rep

    if sf and not isinstance(computed, list):
        computed_cmp = sp.Float(_round_sf(float(sp.N(computed)), int(sf)))
    elif sf:
        computed_cmp = [sp.Float(_round_sf(float(sp.N(c)), int(sf))) for c in computed]
    else:
        computed_cmp = computed
    if not _equal(computed_cmp, expected, tol):
        rep.add("error", qid, "math.mismatch", computed=computed, expected=expected)

    # the printed final answer must show the expected value(s)
    final = str(q.get("final_answer", ""))
    nums = _numbers_in(final)
    for e in expected if isinstance(expected, list) else [expected]:
        try:
            ev = float(sp.N(e))
        except Exception:
            continue
        if ev.is_integer() or sf or tol:
            target = _round_sf(ev, int(sf)) if sf else ev
            if not any(abs(v - target) <= (tol or 1e-6 * max(1, abs(target))) for v in nums):
                if sp.nsimplify(e).is_rational or sf or tol:
                    rep.add("error", qid, "math.printed_missing", final=final, target=target)
    if rep.ok:
        rep.info(qid, "math.verified", expected=expected)
    return rep


def verify_spec_math(spec: dict, timeout: int = 20) -> Report:
    rep = Report()
    for q in spec.get("questions", []):
        rep.extend(verify_question(q, timeout))
    total = sum(int(q.get("marks", 0)) for q in spec.get("questions", []))
    declared = spec.get("total_marks")
    if declared is not None and int(declared) != total:
        rep.add("error", "marks", "math.total_mismatch", declared=declared, total=total)
    return rep


def check_answer(problem_code: str, claimed: str, tolerance: float | None = None) -> Report:
    """Standalone check: recompute with code and compare with a claimed answer."""
    rep = Report()
    computed, err = run_check(problem_code)
    if err:
        rep.add("error", "answer", err[0], **err[1])
        return rep
    try:
        claimed_v = _to_sympy(json.loads(claimed) if claimed.strip().startswith("[") else claimed)
    except Exception as e:  # noqa: BLE001
        rep.add("error", "answer", "math.bad_expected", detail=e)
        return rep
    if _equal(computed, claimed_v, tolerance):
        rep.info("answer", "math.claim_ok", computed=computed)
    else:
        rep.add("error", "answer", "math.claim_mismatch", computed=computed, claimed=claimed_v)
    return rep
