"""검사기가 일부러 넣은 오류를 실제로 잡는지 확인하는 테스트.

실행: python -m pytest tests/  (pytest가 없으면 python tests/test_mathcheck.py)
"""
from __future__ import annotations

import copy
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mathcheck.pipeline import check_all  # noqa: E402
from mathcheck.spec import load_spec  # noqa: E402

SAMPLE = ROOT / "examples" / "sample_quiz.yaml"


def _run(spec: dict):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "t.yaml"
        p.write_text(yaml.safe_dump(spec, allow_unicode=True), encoding="utf-8")
        rep, _ = check_all(p, Path(d) / "out")
        return rep


def _messages(rep) -> str:
    return "\n".join(str(i) for i in rep.issues)


def test_sample_passes():
    rep = _run(load_spec(SAMPLE))
    assert rep.ok, _messages(rep)


def test_wrong_expected_answer_is_caught():
    spec = load_spec(SAMPLE)
    spec["questions"][3]["expected"] = 8  # 진짜 답은 5
    rep = _run(spec)
    assert not rep.ok and "Q4" in _messages(rep)


def test_printed_answer_mismatch_is_caught():
    spec = load_spec(SAMPLE)
    spec["questions"][0]["final_answer"] = "$x = 2$ or $x = 5$"  # 해설지 오타
    rep = _run(spec)
    assert not rep.ok and "Q1" in _messages(rep)


def test_bad_rounding_is_caught():
    spec = load_spec(SAMPLE)
    spec["questions"][2]["expected"] = [3.18, -0.63]
    rep = _run(spec)
    assert not rep.ok and "Q3" in _messages(rep)


def test_out_of_scope_is_caught():
    spec = load_spec(SAMPLE)
    spec["questions"][1]["solution"] += " Alternatively, differentiate: $\\frac{dy}{dx} = 2x - 8$."
    rep = _run(spec)
    assert not rep.ok and "범위 밖" in _messages(rep)


def test_latex_error_is_caught():
    spec = load_spec(SAMPLE)
    spec["questions"][0]["text"] = "Solve $\\frac{x}{2 = 3$."  # 괄호 깨짐
    rep = _run(spec)
    assert not rep.ok and "컴파일" in _messages(rep)


def test_overflow_is_caught():
    spec = load_spec(SAMPLE)
    long_expr = " + ".join(f"{i}x^{{{i}}}" for i in range(1, 40))
    spec["questions"][0]["text"] = f"Simplify \\[ {long_expr} \\] completely."  # 줄바꿈 안 되는 긴 수식
    rep = _run(spec)
    assert not rep.ok and ("여백" in _messages(rep) or "잘려" in _messages(rep))


def test_duplicate_question_is_caught():
    spec = load_spec(SAMPLE)
    dup = copy.deepcopy(spec["questions"][0])
    dup["id"] = 5
    spec["questions"].append(dup)
    spec["total_marks"] = spec["total_marks"] + dup["marks"]
    rep = _run(spec)
    assert not rep.ok and "같은 문제" in _messages(rep)


def test_total_marks_mismatch_is_caught():
    spec = load_spec(SAMPLE)
    spec["total_marks"] = 12
    rep = _run(spec)
    assert not rep.ok and "총점" in _messages(rep)


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("통과", name)
            except AssertionError as e:
                failed += 1
                print("실패", name, e)
    sys.exit(1 if failed else 0)
