from __future__ import annotations

import csv
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "workflows" / "tutoring" / "monthly"))

from aggregate import FIELDS, read_rows, summarize  # noqa: E402


def test_summary_counts():
    rows = [
        ["2026-10-02", "학생A", "IGCSE", "Quadratics", "1", "정답", "", "", "", ""],
        ["2026-10-02", "학생A", "IGCSE", "Quadratics", "2", "오답", "5", "-5", "부호실수", ""],
        ["2026-10-09", "학생A", "IGCSE", "Trig", "3", "판독불가", "", "", "", ""],
        ["2026-10-09", "학생A", "IGCSE", "Trig", "4", "정답", "", "", "", ""],
        ["2026-09-30", "학생A", "IGCSE", "Trig", "9", "오답", "", "", "", ""],  # 다른 달
    ]
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "log.csv"
        with open(p, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(FIELDS)
            w.writerows(rows)
        s = summarize(read_rows([str(p)]), "2026-10")["학생A"]
    assert s["problems_graded"] == 3
    assert s["unreadable"] == 1
    assert s["accuracy"] == round(2 / 3, 3)
    assert s["error_types"] == {"부호실수": 1}
    assert s["weekly_accuracy"] == {"1주차": 0.5, "2주차": 1.0}


if __name__ == "__main__":
    test_summary_counts()
    print("통과 test_summary_counts")
