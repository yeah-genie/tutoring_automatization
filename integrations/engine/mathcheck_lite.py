"""mathcheck_lite — single-file worksheet checker for AI chat sandboxes (ChatGPT, Claude).

Needs only sympy (and the standard library). Usage inside a code sandbox:

    import mathcheck_lite as mc
    report = mc.check_worksheet(questions, curriculum="ib_aa", chapters=["calculus"], total_marks=40)
    print(mc.format_report(report, lang="en"))

Each question is a dict:
    id           question number as printed, e.g. "3(b)"
    text         question text (used for the syllabus check)
    check        Python/sympy code that solves the question from its own conditions and sets `result`
                 (a list = several answers in any order; a tuple = ordered, e.g. coordinates)
    answer_key   the answer printed on the worksheet's answer key (string/number/list), or None if there is none
    sf / dp      (optional) significant figures / decimal places the answer is given to
    tolerance    (optional) absolute tolerance for decimal answers
    marks        (optional) marks for the question
    notes        (optional) anything else the reviewer noticed (ambiguity, typo, missing data)

Verdicts per question:
    ok            computed answer matches the answer key
    wrong_key     computed answer does NOT match the answer key
    no_key        there is no answer key; the computed answer is reported
    check_failed  the check code could not run (fix the code, do not guess)
"""
from __future__ import annotations

import json
import os
import re
from math import floor, log10

import sympy as sp

HERE = os.path.dirname(os.path.abspath(__file__))
_SYMS = dict(zip("x y z t n k a b c".split(), sp.symbols("x y z t n k a b c")))


# ---------- answers ----------
def run_check(code: str):
    ns: dict = {}
    env = {**{k: getattr(sp, k) for k in dir(sp) if not k.startswith("_")}, **_SYMS}
    exec(compile(code, "<check>", "exec"), env, ns)  # noqa: S102 (runs inside the chat's own sandbox)
    if "result" not in ns:
        raise ValueError("check code did not set `result`")
    r = ns["result"]
    if isinstance(r, tuple):  # tuple = ordered (coordinates, vectors)
        return sp.Tuple(*r)
    if isinstance(r, (set, frozenset)):
        r = list(r)
    if isinstance(r, list):  # list = several answers, any order
        return [sp.sympify(i) for i in r]
    return sp.sympify(r)


def parse_answer(v):
    if v is None:
        return None
    if isinstance(v, (list, tuple, set)):
        return [parse_answer(i) for i in v]
    if isinstance(v, bool):
        return sp.true if v else sp.false
    if isinstance(v, int):
        return sp.Integer(v)
    if isinstance(v, float):
        return sp.Float(v)
    s = str(v).strip()
    s = re.sub(r"^\s*[a-zA-Z]\s*=\s*", "", s)  # "x = 5" -> "5"
    s = re.sub(r"\s*\+\s*[cC]\s*$", "", s)  # drop "+ C" of an indefinite integral
    s = re.sub(r"\$|\\left|\\right|\\,", "", s).replace("\\pi", "pi").replace("\\sqrt", "sqrt").replace("{", "(").replace("}", ")")
    s = s.replace("^", "**").replace("−", "-").replace("×", "*").replace("÷", "/").replace("√", "sqrt").replace("π", "pi")
    s = s.replace("{,}", "").replace(",", "") if re.fullmatch(r"[\d,\.\s{}]+", s) else s
    if re.search(r"\bor\b|;", s) or ("," in s and not s.startswith("(")):
        return [parse_answer(p) for p in re.split(r"\bor\b|;|,", s) if p.strip()]
    from sympy.parsing.sympy_parser import (implicit_multiplication_application, parse_expr,
                                            standard_transformations)
    v = parse_expr(s, local_dict={"e": sp.E, "E": sp.E},
                      transformations=standard_transformations + (implicit_multiplication_application,))
    return sp.Tuple(*v) if isinstance(v, tuple) else v


def _round(v: float, sf=None, dp=None) -> float:
    if dp is not None:
        return round(v, int(dp))
    if sf is not None and v != 0:
        return round(v, int(sf) - 1 - floor(log10(abs(v))))
    return v


def _num(e):
    try:
        c = complex(sp.N(e))
        return c.real if abs(c.imag) < 1e-12 else c
    except Exception:
        return None


def equal(a, b, tol=None, sf=None, dp=None) -> bool:
    if isinstance(a, sp.Tuple) or isinstance(b, sp.Tuple):
        a, b = list(a) if isinstance(a, sp.Tuple) else [a], list(b) if isinstance(b, sp.Tuple) else [b]
        return len(a) == len(b) and all(equal(i, j, tol, sf, dp) for i, j in zip(a, b))
    if isinstance(a, list) or isinstance(b, list):
        a = a if isinstance(a, list) else [a]
        b = b if isinstance(b, list) else [b]
        if len(a) != len(b):
            return False
        rest = list(b)
        for item in a:
            hit = next((j for j, o in enumerate(rest) if equal(item, o, tol, sf, dp)), None)
            if hit is None:
                return False
            rest.pop(hit)
        return True
    if tol is None and sf is None and dp is None:
        try:
            if sp.simplify(sp.nsimplify(a) - sp.nsimplify(b)) == 0:
                return True
        except Exception:
            pass
    fa, fb = _num(a), _num(b)
    if fa is None or fb is None:
        return str(a) == str(b)
    if isinstance(fa, complex) or isinstance(fb, complex):
        return abs(complex(fa) - complex(fb)) <= (tol or 1e-9)
    if sf is not None or dp is not None:
        if abs(_round(fa, sf, dp) - fb) <= 1e-9 * max(1, abs(fb)):
            return True
        # answer key given more precisely than asked is fine; less precisely is not
        return tol is not None and abs(fa - fb) <= tol
    return abs(fa - fb) <= (tol if tol is not None else 1e-9 * max(1.0, abs(fb)))


def check_question(q: dict) -> dict:
    out = {"id": str(q.get("id", "?")), "marks": q.get("marks"), "notes": q.get("notes") or ""}
    try:
        computed = run_check(q["check"])
    except Exception as e:  # noqa: BLE001
        return {**out, "verdict": "check_failed", "detail": f"{type(e).__name__}: {e}"}
    out["computed"] = _pretty(computed, q.get("sf"), q.get("dp"))
    key = q.get("answer_key")
    if key in (None, ""):
        return {**out, "verdict": "no_key"}
    try:
        key_v = parse_answer(key)
    except Exception as e:  # noqa: BLE001
        return {**out, "verdict": "check_failed", "detail": f"could not read answer key '{key}': {e}"}
    out["answer_key"] = str(key)
    ok = equal(computed, key_v, q.get("tolerance"), q.get("sf"), q.get("dp"))
    return {**out, "verdict": "ok" if ok else "wrong_key"}


def _pretty(v, sf=None, dp=None):
    if isinstance(v, list):
        return "[" + ", ".join(_pretty(i, sf, dp) for i in v) + "]"
    if (sf or dp) and _num(v) is not None and not isinstance(_num(v), complex):
        r = _round(float(_num(v)), sf, dp)
        return f"{v}  (≈ {r:g})"
    return str(v)


# ---------- syllabus scope ----------
RAW = "https://raw.githubusercontent.com/yeah-genie/tutoring_automatization/main/integrations/engine"


def load_curricula() -> dict:
    """All curricula from curricula.json next to this file, or the curricula/ folder, or {}."""
    path = os.path.join(HERE, "curricula.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    out = {}
    folder = os.path.join(HERE, "curricula")
    if os.path.isdir(folder):
        for name in sorted(os.listdir(folder)):
            if name.endswith(".json"):
                with open(os.path.join(folder, name), encoding="utf-8") as f:
                    out[name[:-5]] = json.load(f)
    return out


def list_curricula() -> dict:
    return {k: v.get("name", k) for k, v in load_curricula().items()}


def _allowed(cur: dict, selected: set) -> set:
    chapters, order = cur["chapters"], list(cur["chapters"])
    out, stack = set(), [c for c in selected if c in chapters]
    while stack:
        ch = stack.pop()
        if ch in out:
            continue
        out.add(ch)
        info = chapters[ch]
        if "requires" in info:
            stack += info["requires"] or []
        elif cur.get("cumulative"):
            stack += order[: order.index(ch)]
    return out


def check_scope(questions: list, curriculum, chapters: list) -> list:
    """curriculum: a code like "ib_aa" (looked up locally) or the curriculum dict itself
    (e.g. json.loads of RAW + "/curricula/ib_aa.json", for sandboxes without the data file)."""
    if isinstance(curriculum, dict):
        cur = curriculum
    else:
        curs = load_curricula()
        if curriculum not in curs:
            return [{"id": "-", "problem": f"curriculum '{curriculum}' not available here "
                     f"(have: {', '.join(curs) or 'none'}); pass the curriculum dict instead, see {RAW}/curricula/"}]
        cur = curs[curriculum]
    unknown = [c for c in chapters if c not in cur["chapters"]]
    found = [{"id": "-", "problem": f"unknown chapter code '{c}'"} for c in unknown]
    allowed = _allowed(cur, set(chapters))
    allowed_kw = {k.lower() for c in allowed for k in cur["chapters"][c].get("keywords", [])}
    for q in questions:
        blob = " ".join(str(q.get(k, "")) for k in ("text", "solution", "answer_key")).lower()
        for ch, info in cur["chapters"].items():
            if ch in allowed:
                continue
            for kw in info.get("keywords", []):
                k = kw.lower()
                if k in allowed_kw:
                    continue
                pat = (r"\b" if k[:1].isalnum() else "") + re.escape(k) + (r"\b" if k[-1:].isalnum() else "")
                if re.search(pat, blob):
                    found.append({"id": str(q.get("id", "?")), "problem": f"'{kw}' is from {info.get('title', ch).split(':')[0]}"})
    return found


# ---------- whole worksheet ----------
def check_worksheet(questions: list, curriculum=None, chapters: list | None = None,
                    total_marks: int | None = None) -> dict:
    results = [check_question(q) for q in questions]
    rep = {"questions": results, "scope": [], "marks": None}
    if curriculum and chapters:
        rep["scope"] = check_scope(questions, curriculum, chapters)
    marks = [q.get("marks") for q in questions if isinstance(q.get("marks"), (int, float))]
    if total_marks is not None and marks:
        rep["marks"] = {"declared": total_marks, "sum": sum(marks), "ok": sum(marks) == total_marks}
    ids = [str(q.get("id")) for q in questions]
    rep["duplicate_ids"] = sorted({i for i in ids if ids.count(i) > 1})
    return rep


T = {
    "en": {"ok": "OK", "wrong_key": "ANSWER KEY WRONG", "no_key": "no key; computed", "check_failed": "COULD NOT CHECK",
           "title": "Worksheet check", "scope": "Outside the selected syllabus", "marks": "Marks: printed total {d}, questions add to {s}",
           "summary": "{n} questions: {ok} OK, {bad} answer-key problems, {fail} not checked, {nokey} without key"},
    "ko": {"ok": "정상", "wrong_key": "정답지 오류", "no_key": "정답지 없음, 계산값", "check_failed": "검사 실패",
           "title": "워크시트 검사 결과", "scope": "선택한 범위 밖 개념", "marks": "배점: 표기된 총점 {d}, 문항 합 {s}",
           "summary": "{n}문항: 정상 {ok}, 정답지 문제 {bad}, 검사 못함 {fail}, 정답지 없음 {nokey}"},
}


def format_report(rep: dict, lang: str = "en") -> str:
    t = T.get(lang[:2], T["en"])
    qs = rep["questions"]
    count = lambda v: sum(q["verdict"] == v for q in qs)  # noqa: E731
    lines = [f"## {t['title']}",
             t["summary"].format(n=len(qs), ok=count("ok"), bad=count("wrong_key"), fail=count("check_failed"), nokey=count("no_key")), ""]
    for q in qs:
        v = q["verdict"]
        line = f"- Q{q['id']}: {t[v]}"
        if v == "wrong_key":
            line += f" — key: {q['answer_key']} / computed: {q['computed']}"
        elif v == "no_key":
            line += f" {q['computed']}"
        elif v == "ok":
            line += f" ({q['computed']})"
        else:
            line += f" — {q.get('detail', '')}"
        if q.get("notes"):
            line += f"  · {q['notes']}"
        lines.append(line)
    if rep.get("scope"):
        lines += ["", f"**{t['scope']}**"] + [f"- Q{s['id']}: {s['problem']}" for s in rep["scope"]]
    if rep.get("marks") and not rep["marks"]["ok"]:
        lines += ["", t["marks"].format(d=rep["marks"]["declared"], s=rep["marks"]["sum"])]
    if rep.get("duplicate_ids"):
        lines += ["", "Duplicate question numbers: " + ", ".join(rep["duplicate_ids"])]
    return "\n".join(lines)
