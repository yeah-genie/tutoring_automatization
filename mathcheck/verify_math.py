"""수학 정답 검사.

문항마다 세 가지가 서로 맞는지 본다.
  1. check: 문제 조건만 가지고 답을 계산하는 파이썬(sympy) 코드. 마지막에 result 변수에 답을 넣는다.
  2. expected: 출제자가 정한 정답 (sympy가 읽을 수 있는 식, 숫자, 또는 리스트)
  3. final_answer: 해설지에 실제로 인쇄되는 최종 답 문자열

check 결과 == expected 이고, final_answer 안에 expected가 드러나야 통과.
check 코드는 별도 프로세스에서 시간 제한을 두고 실행한다.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import textwrap

import sympy as sp

from .spec import Report

RUNNER = r'''
import json, sys
from sympy import *
x, y, z, t, n, k, a, b, c = symbols("x y z t n k a b c")
ns = {}
exec(compile(sys.stdin.read(), "<check>", "exec"), globals(), ns)
if "result" not in ns:
    print(json.dumps({"error": "check 코드에 result 변수가 없음"}))
else:
    r = ns["result"]
    if isinstance(r, (set, frozenset, tuple)):
        r = list(r)
    print(json.dumps({"result": srepr(r) if not isinstance(r, list) else [srepr(i) for i in r]}))
'''


def run_check(code: str, timeout: int = 20) -> tuple[object | None, str | None]:
    try:
        p = subprocess.run(
            [sys.executable, "-I", "-c", RUNNER],
            input=textwrap.dedent(code),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return None, f"check 코드가 {timeout}초 안에 끝나지 않음"
    if p.returncode != 0:
        last = (p.stderr.strip().splitlines() or ["알 수 없는 오류"])[-1]
        return None, f"check 코드 실행 오류: {last}"
    try:
        out = json.loads(p.stdout.strip().splitlines()[-1])
    except Exception:
        return None, "check 코드 출력 형식 오류"
    if "error" in out:
        return None, out["error"]
    r = out["result"]
    if isinstance(r, list):
        return [sp.sympify(eval(s, vars(sp))) for s in r], None  # noqa: S307 (srepr round-trip)
    return sp.sympify(eval(r, vars(sp))), None  # noqa: S307


def _to_sympy(v):
    if isinstance(v, (list, tuple, set)):
        return [_to_sympy(i) for i in v]
    if isinstance(v, (int, float)):
        return sp.nsimplify(v) if isinstance(v, int) else sp.Float(v)
    return sp.sympify(str(v).replace("^", "**"))


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
        diff = sp.simplify(sp.nsimplify(a) - sp.nsimplify(b)) if tol is None else None
        if diff == 0:
            return True
        fa, fb = complex(sp.N(a)), complex(sp.N(b))
        limit = tol if tol is not None else 1e-9 * max(1.0, abs(fb))
        return abs(fa - fb) <= limit
    except Exception:
        return str(a) == str(b)


def _round_sf(v: float, sf: int) -> float:
    if v == 0:
        return 0.0
    from math import floor, log10

    return round(v, sf - 1 - floor(log10(abs(v))))


def _numbers_in(text: str) -> list[float]:
    cleaned = text.replace("{,}", "").replace(",", "")
    # '-'는 앞에 글자·숫자·닫는 괄호가 없을 때만 부호로 본다 (x-4의 4는 양수)
    return [float(m) for m in re.findall(r"(?:(?<![\w)\]}])-)?\d+(?:\.\d+)?", cleaned)]


def verify_question(q: dict) -> Report:
    rep = Report()
    qid = f"Q{q.get('id', '?')}"
    tol = q.get("tolerance")
    sf = q.get("sf")

    computed, err = run_check(q.get("check", ""))
    if err:
        rep.add("error", qid, err)
        return rep
    try:
        expected = _to_sympy(q.get("expected"))
    except Exception as e:  # noqa: BLE001
        rep.add("error", qid, f"expected를 식으로 읽을 수 없음: {e}")
        return rep

    if sf and not isinstance(computed, list):
        computed_cmp = sp.Float(_round_sf(float(sp.N(computed)), int(sf)))
    else:
        computed_cmp = computed
    if not _equal(computed_cmp, expected, tol):
        rep.add("error", qid, f"계산 결과 {computed} ≠ 정답 {expected}. 정답이나 문제 조건이 틀렸을 수 있음")

    # 해설지에 인쇄될 최종 답이 정답과 같은 숫자를 담고 있는지
    final = str(q.get("final_answer", ""))
    exp_list = expected if isinstance(expected, list) else [expected]
    nums = _numbers_in(final)
    for e in exp_list:
        try:
            ev = float(sp.N(e))
        except Exception:
            continue
        if ev.is_integer() or sf or tol:
            target = _round_sf(ev, int(sf)) if sf else ev
            if not any(abs(v - target) <= (tol or 1e-6 * max(1, abs(target))) for v in nums):
                if sp.nsimplify(e).is_rational or sf or tol:
                    rep.add("error", qid, f"해설지 최종 답 '{final}'에 정답 {target}이(가) 보이지 않음")
    if not rep.issues:
        rep.notes.append(f"{qid} 정답 확인: {expected}")
    return rep


def verify_spec_math(spec: dict) -> Report:
    rep = Report()
    for q in spec.get("questions", []):
        rep.extend(verify_question(q))
    total = sum(int(q.get("marks", 0)) for q in spec.get("questions", []))
    declared = spec.get("total_marks")
    if declared is not None and int(declared) != total:
        rep.add("error", "배점", f"표지에 적힌 총점 {declared} ≠ 문항 배점 합 {total}")
    return rep


def check_answer(problem_code: str, claimed: str, tolerance: float | None = None) -> Report:
    """MCP에서 단독으로 쓰는 간단 검사: 코드로 계산한 값과 주장한 답 비교."""
    rep = Report()
    computed, err = run_check(problem_code)
    if err:
        rep.add("error", "계산", err)
        return rep
    claimed_v = _to_sympy(json.loads(claimed) if claimed.strip().startswith("[") else claimed)
    if _equal(computed, claimed_v, tolerance):
        rep.notes.append(f"일치: {computed}")
    else:
        rep.add("error", "계산", f"계산 결과 {computed} ≠ 주장한 답 {claimed_v}")
    return rep
