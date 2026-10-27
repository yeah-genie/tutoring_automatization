"""문항 중복 검사: 같은 퀴즈 안, 그리고 예전에 낸 문항 기록과 비교한다.

기록 파일(bank.jsonl)에는 문항 본문의 지문(해시)과 날짜만 남기고, 학생 이름은 저장하지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path

from .spec import Report


def fingerprint(text: str) -> str:
    norm = re.sub(r"\s+", " ", re.sub(r"\\[a-zA-Z]+|[{}$]", " ", text)).strip().lower()
    return hashlib.sha1(norm.encode()).hexdigest()[:16]


def check_duplicates(spec: dict, bank_path: str | Path | None = None) -> Report:
    rep = Report()
    seen: dict[str, str] = {}
    for q in spec.get("questions", []):
        fp = fingerprint(q.get("text", ""))
        qid = f"Q{q.get('id', '?')}"
        if fp in seen:
            rep.add("error", qid, f"{seen[fp]}와(과) 같은 문제")
        seen[fp] = qid
    if bank_path and Path(bank_path).exists():
        old = {}
        for line in Path(bank_path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                old[rec["fp"]] = rec.get("date", "?")
        for fp, qid in seen.items():
            if fp in old:
                rep.add("warning", qid, f"{old[fp]}에 낸 적 있는 문제와 같음")
    return rep


def record(spec: dict, bank_path: str | Path) -> None:
    with open(bank_path, "a", encoding="utf-8") as f:
        for q in spec.get("questions", []):
            f.write(json.dumps({"fp": fingerprint(q.get("text", "")), "date": date.today().isoformat()}) + "\n")
