"""Duplicate detection: within one quiz, and against a history file of questions already used.

The history file (JSONL) stores only a fingerprint (hash) of each question text and a date —
no student names, no question text.
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
        fp = fingerprint(str(q.get("text", "")))
        qid = f"Q{q.get('id', '?')}"
        if fp in seen:
            rep.add("error", qid, "dup.within", other=seen[fp])
        else:
            seen[fp] = qid
    if bank_path and Path(bank_path).exists():
        old = {}
        for line in Path(bank_path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                old[rec["fp"]] = rec.get("date", "?")
        for fp, qid in seen.items():
            if fp in old:
                rep.add("warning", qid, "dup.bank", date=old[fp])
    return rep


def record(spec: dict, bank_path: str | Path) -> None:
    with open(bank_path, "a", encoding="utf-8") as f:
        for q in spec.get("questions", []):
            f.write(json.dumps({"fp": fingerprint(str(q.get("text", ""))), "date": date.today().isoformat()}) + "\n")
