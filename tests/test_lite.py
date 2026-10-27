"""The single-file engine used by the ChatGPT GPT and the Claude skill.

The demo worksheet (examples/demo_worksheet.tex) has four planted problems:
Q2 rounded wrongly (4.58 not 4.59), Q4 wrong key (10 not 12), Q5 is HL content on an SL sheet,
and the printed total (20) does not match the marks (19).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "integrations" / "engine"))

import mathcheck_lite as mc  # noqa: E402

DEMO = [
    {"id": "1", "marks": 3, "text": "Given f(x) = 3x^4 - 5x^2 + 2x, find f'(x).",
     "check": "result = diff(3*x**4 - 5*x**2 + 2*x, x)", "answer_key": "12x^3 - 10x + 2"},
    {"id": "2", "marks": 3, "text": "Solve 2^{x+1} = 48.", "sf": 3,
     "check": "result = solve(Eq(2**(x+1), 48), x)[0]", "answer_key": "x = 4.59"},
    {"id": "3", "marks": 2, "text": "A geometric series has first term 6 and common ratio 1/3. Find its sum to infinity.",
     "check": "result = Rational(6) / (1 - Rational(1, 3))", "answer_key": "9"},
    {"id": "4", "marks": 3, "text": "Evaluate \\int_0^2 (3x^2 + 1) dx.",
     "check": "result = integrate(3*x**2 + 1, (x, 0, 2))", "answer_key": "12"},
    {"id": "5", "marks": 4, "text": "Find \\int x e^{x} dx using integration by parts.",
     "check": "result = integrate(x*exp(x), x)", "answer_key": "xe^x - e^x + C"},
    {"id": "6", "marks": 4, "text": "Find the x-coordinates of the stationary points of y = x^3 - 6x^2 + 9x + 1.",
     "check": "result = solve(diff(x**3 - 6*x**2 + 9*x + 1, x), x)", "answer_key": "x = 1, x = 3"},
]


def test_demo_worksheet():
    rep = mc.check_worksheet(DEMO, curriculum="ib_aa", chapters=["calculus"], total_marks=20)
    verdicts = {q["id"]: q["verdict"] for q in rep["questions"]}
    assert verdicts == {"1": "ok", "2": "wrong_key", "3": "ok", "4": "wrong_key", "5": "ok", "6": "ok"}, verdicts
    assert any(s["id"] == "5" for s in rep["scope"]), rep["scope"]
    assert rep["marks"] == {"declared": 20, "sum": 19, "ok": False}
    text = mc.format_report(rep, "ko")
    assert "정답지 오류" in text


def test_answer_formats():
    eq = lambda key, code, **kw: mc.check_question({"id": 1, "check": code, "answer_key": key, **kw})["verdict"]  # noqa: E731
    assert eq("3,000", "result = 3000") == "ok"
    assert eq("(2, 3)", "result = (2, 3)") == "ok"
    assert eq("(3, 2)", "result = (2, 3)") == "wrong_key"  # coordinates are ordered
    assert eq("$\\frac{\\sqrt{2}}{2}$".replace("\\frac{\\sqrt{2}}{2}", "\\sqrt{2}/2"), "result = sqrt(2)/2") == "ok"
    assert eq("2π", "result = 2*pi") == "ok"
    assert eq("−5 or 2", "result = solve(x**2 + 3*x - 10, x)") == "ok"
    assert eq("27.3", "result = 27.27", dp=1) == "ok"
    assert mc.check_question({"id": 1, "check": "y = 2", "answer_key": "2"})["verdict"] == "check_failed"


if __name__ == "__main__":
    test_demo_worksheet()
    test_answer_formats()
    print("통과 test_lite")
