"""월간 집계: 하루 단위 채점 기록(CSV 여러 개)을 학생별 요약으로 만든다.

기록 CSV 열 (매일 채점 작업이 이 형식으로 저장)
  date, student, course, unit, problem, result, student_answer, correct_answer, error_type, note
  result: 정답 | 오답 | 미풀이 | 판독불가

사용
  python monthly/aggregate.py logs/*.csv --month 2026-10 > summary.json

출력은 학생별 JSON. 학부모 피드백 문장은 이 숫자를 근거로 사람이 검토할 초안을 만든다.
판독불가는 정답률 계산에서 뺀다.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import date

FIELDS = ["date", "student", "course", "unit", "problem", "result",
          "student_answer", "correct_answer", "error_type", "note"]


def read_rows(paths: list[str]) -> list[dict]:
    rows = []
    for p in paths:
        with open(p, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                if r.get("student"):
                    rows.append({k: (r.get(k) or "").strip() for k in FIELDS})
    return rows


def week_of(d: str) -> str:
    y, m, dd = map(int, d.split("-"))
    return f"{(dd - 1) // 7 + 1}주차"


def summarize(rows: list[dict], month: str) -> dict:
    by_student: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r["date"].startswith(month):
            by_student[r["student"]].append(r)
    out = {}
    for name, rs in sorted(by_student.items()):
        graded = [r for r in rs if r["result"] in ("정답", "오답", "미풀이")]
        correct = sum(r["result"] == "정답" for r in graded)
        weekly = defaultdict(lambda: [0, 0])
        for r in graded:
            w = week_of(r["date"])
            weekly[w][1] += 1
            weekly[w][0] += r["result"] == "정답"
        wrong = [r for r in graded if r["result"] != "정답"]
        unit_wrong = Counter(r["unit"] for r in wrong if r["unit"])
        unit_total = Counter(r["unit"] for r in graded if r["unit"])
        out[name] = {
            "course": Counter(r["course"] for r in rs if r["course"]).most_common(1)[0][0] if any(r["course"] for r in rs) else "미확인",
            "submission_days": len({r["date"] for r in rs}),
            "problems_graded": len(graded),
            "unreadable": sum(r["result"] == "판독불가" for r in rs),
            "accuracy": round(correct / len(graded), 3) if graded else None,
            "weekly_accuracy": {w: round(c / t, 3) for w, (c, t) in sorted(weekly.items()) if t},
            "error_types": dict(Counter(r["error_type"] for r in wrong if r["error_type"]).most_common()),
            "weak_units": [
                {"unit": u, "wrong": n, "total": unit_total[u]} for u, n in unit_wrong.most_common(3)
            ],
            "examples": [
                {k: r[k] for k in ("date", "unit", "problem", "student_answer", "correct_answer", "error_type")}
                for r in wrong[:5]
            ],
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", nargs="+")
    ap.add_argument("--month", default=date.today().strftime("%Y-%m"))
    args = ap.parse_args()
    json.dump(summarize(read_rows(args.csv), args.month), sys.stdout, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
