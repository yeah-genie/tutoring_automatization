"""퀴즈 사양(YAML) 읽기와 형식 확인.

퀴즈 하나 = YAML 파일 하나. 예시는 examples/sample_quiz.yaml.

필수 항목
  title, curriculum, chapters, questions
문항(question) 필수 항목
  id, marks, text, check, expected, final_answer, solution
선택 항목
  diagram (TikZ 코드), concepts (개념 태그), tolerance (소수 답 허용 오차), sf (유효숫자)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

REQUIRED_TOP = ["title", "curriculum", "chapters", "questions"]
REQUIRED_Q = ["id", "marks", "text", "check", "expected", "final_answer", "solution"]


@dataclass
class Issue:
    level: str  # "error" | "warning"
    where: str  # 예: "Q3", "LaTeX", "scope"
    message: str

    def __str__(self) -> str:
        tag = "오류" if self.level == "error" else "주의"
        return f"[{tag}] {self.where}: {self.message}"


@dataclass
class Report:
    issues: list[Issue] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def add(self, level: str, where: str, message: str) -> None:
        self.issues.append(Issue(level, where, message))

    @property
    def ok(self) -> bool:
        return not any(i.level == "error" for i in self.issues)

    def extend(self, other: "Report") -> None:
        self.issues += other.issues
        self.notes += other.notes

    def to_text(self) -> str:
        head = "통과 ✅" if self.ok else "실패 ❌ (학생에게 내면 안 됨)"
        lines = [f"검사 결과: {head}"]
        lines += [str(i) for i in self.issues]
        lines += [f"- {n}" for n in self.notes]
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "issues": [i.__dict__ for i in self.issues],
            "notes": self.notes,
        }


def load_spec(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def validate_spec(spec: dict) -> Report:
    rep = Report()
    for key in REQUIRED_TOP:
        if key not in spec:
            rep.add("error", "사양", f"'{key}' 항목이 없음")
    qs = spec.get("questions") or []
    if not qs:
        rep.add("error", "사양", "문항이 하나도 없음")
    ids = set()
    for q in qs:
        qid = f"Q{q.get('id', '?')}"
        for key in REQUIRED_Q:
            if key not in q or q[key] in (None, ""):
                rep.add("error", qid, f"'{key}' 항목이 비어 있음")
        if q.get("id") in ids:
            rep.add("error", qid, "문항 번호가 중복됨")
        ids.add(q.get("id"))
        if not isinstance(q.get("marks"), int) or q.get("marks", 0) <= 0:
            rep.add("error", qid, "배점(marks)은 1 이상의 정수여야 함")
    return rep
