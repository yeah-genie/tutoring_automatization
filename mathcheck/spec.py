"""Quiz spec (YAML) loading, validation, and the Report/Issue types.

One quiz = one YAML file (or a dict). See docs/spec-format.md and examples/sample_quiz.yaml.

Required top-level keys: title, questions
Recommended: curriculum, chapters (enables the scope check), total_marks
Required per question: id, marks, text, check, expected, final_answer, solution
Optional per question: diagram, trap, tolerance, sf, answer_lines
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .i18n import t

REQUIRED_TOP = ["title", "questions"]
REQUIRED_Q = ["id", "marks", "text", "check", "expected", "final_answer", "solution"]


@dataclass
class Issue:
    level: str  # "error" | "warning" | "info"
    where: str  # e.g. "Q3", "quiz.tex", "scope", "marks", "spec"
    code: str  # stable machine-readable code, see i18n.MESSAGES
    params: dict = field(default_factory=dict)

    def message(self, lang: str | None = None) -> str:
        return t(self.code, lang, **self.params)

    def render(self, lang: str | None = None) -> str:
        return f"[{t('level.' + self.level, lang)}] {self.where}: {self.message(lang)}"

    def __str__(self) -> str:
        return self.render()


@dataclass
class Report:
    issues: list[Issue] = field(default_factory=list)

    def add(self, level: str, where: str, code: str, **params) -> None:
        self.issues.append(Issue(level, where, code, {k: str(v) for k, v in params.items()}))

    def info(self, where: str, code: str, **params) -> None:
        self.add("info", where, code, **params)

    @property
    def ok(self) -> bool:
        return not any(i.level == "error" for i in self.issues)

    @property
    def codes(self) -> list[str]:
        return [i.code for i in self.issues if i.level != "info"]

    def extend(self, other: "Report") -> None:
        self.issues += other.issues

    def to_text(self, lang: str | None = None) -> str:
        status = t("report.pass" if self.ok else "report.fail", lang)
        lines = [t("report.head", lang, status=status)]
        order = {"error": 0, "warning": 1, "info": 2}
        lines += [i.render(lang) for i in sorted(self.issues, key=lambda i: order.get(i.level, 3))]
        return "\n".join(lines)

    def to_dict(self, lang: str | None = None) -> dict:
        return {
            "ok": self.ok,
            "errors": sum(i.level == "error" for i in self.issues),
            "warnings": sum(i.level == "warning" for i in self.issues),
            "issues": [
                {"level": i.level, "where": i.where, "code": i.code, "message": i.message(lang), "params": i.params}
                for i in self.issues
            ],
        }


def load_spec(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def parse_spec(text: str) -> dict:
    return yaml.safe_load(text)


def validate_spec(spec: object) -> Report:
    rep = Report()
    if not isinstance(spec, dict):
        rep.add("error", "spec", "spec.unreadable", detail="top level must be a mapping")
        return rep
    for key in REQUIRED_TOP:
        if key not in spec:
            rep.add("error", "spec", "spec.missing_key", key=key)
    qs = spec.get("questions") or []
    if not qs:
        rep.add("error", "spec", "spec.no_questions")
    ids = set()
    for q in qs:
        if not isinstance(q, dict):
            rep.add("error", "spec", "spec.unreadable", detail="each question must be a mapping")
            continue
        qid = f"Q{q.get('id', '?')}"
        for key in REQUIRED_Q:
            if key not in q or q[key] in (None, ""):
                rep.add("error", qid, "spec.empty_field", key=key)
        if q.get("id") in ids:
            rep.add("error", qid, "spec.duplicate_id")
        ids.add(q.get("id"))
        if not isinstance(q.get("marks"), int) or q.get("marks", 0) <= 0:
            rep.add("error", qid, "spec.bad_marks")
    return rep
