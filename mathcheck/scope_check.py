"""Syllabus scope check.

A curriculum file lists, per chapter, keywords for concepts that are first introduced in that
chapter. If a keyword from a chapter that was NOT selected appears in a question, solution or
diagram, it is flagged. Keyword matching is a safety net, not a proof that a quiz is in scope.

Where curriculum files are looked up (first match wins):
  1. `curriculum` in the spec is itself a path to a .yaml file
  2. directories in the MATHCHECK_CURRICULA env var (os.pathsep separated)
  3. ./curricula in the current working directory
  4. curricula bundled with mathcheck (mathcheck/curricula/)
See docs/writing-curricula.md for the file format.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import yaml

from .spec import Report

BUNDLED_DIR = Path(__file__).resolve().parent / "curricula"


def search_dirs() -> list[Path]:
    dirs = [Path(d) for d in os.environ.get("MATHCHECK_CURRICULA", "").split(os.pathsep) if d]
    return dirs + [Path.cwd() / "curricula", BUNDLED_DIR]


def find_curriculum(name: str) -> Path | None:
    p = Path(name)
    if p.suffix in (".yaml", ".yml") and p.exists():
        return p
    for d in search_dirs():
        for ext in (".yaml", ".yml"):
            cand = d / f"{name}{ext}"
            if cand.exists():
                return cand
    return None


def list_curricula() -> dict[str, str]:
    out: dict[str, str] = {}
    for d in reversed(search_dirs()):  # earlier dirs override later ones
        if d.is_dir():
            for f in sorted(d.glob("*.y*ml")):
                try:
                    out[f.stem] = (yaml.safe_load(f.read_text(encoding="utf-8")) or {}).get("name", f.stem)
                except Exception:  # noqa: BLE001
                    continue
    return out


def load_curriculum(name: str) -> dict:
    path = find_curriculum(name)
    if path is None:
        raise FileNotFoundError(name)
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def allowed_chapters(cur: dict, selected: set[str]) -> set[str]:
    """Selected chapters plus everything they build on.

    A chapter's prerequisites are its `requires:` list; if it has none and the curriculum says
    `cumulative: true`, every earlier chapter in file order is a prerequisite.
    """
    chapters = cur["chapters"]
    order = list(chapters)
    cumulative = bool(cur.get("cumulative"))

    def prereqs(ch: str) -> list[str]:
        info = chapters.get(ch) or {}
        if "requires" in info:
            return list(info.get("requires") or [])
        if cumulative and ch in order:
            return order[: order.index(ch)]
        return []

    out: set[str] = set()
    stack = [c for c in selected if c in chapters]
    while stack:
        ch = stack.pop()
        if ch in out:
            continue
        out.add(ch)
        stack += prereqs(ch)
    return out


def check_scope(spec: dict) -> Report:
    rep = Report()
    name = spec.get("curriculum")
    if not name:
        return rep
    try:
        cur = load_curriculum(str(name))
    except FileNotFoundError:
        rep.add("warning", "scope", "scope.no_curriculum", name=name)
        return rep
    chapters = cur["chapters"]
    selected = set(spec.get("chapters", []))
    for u in sorted(selected - set(chapters)):
        rep.add("error", "scope", "scope.unknown_chapter", chapter=u, curriculum=name)
    allowed = selected if spec.get("scope_mode") == "strict" else allowed_chapters(cur, selected)
    # a keyword that belongs to an allowed chapter is fine even if another chapter lists it too
    allowed_kw = {kw.lower() for ch in allowed & set(chapters) for kw in chapters[ch].get("keywords", [])}
    for q in spec.get("questions", []):
        qid = f"Q{q.get('id', '?')}"
        blob = " ".join(str(q.get(k, "")) for k in ("text", "solution", "final_answer", "diagram", "trap")).lower()
        for ch, info in chapters.items():
            if ch in allowed:
                continue
            for kw in info.get("keywords", []):
                k = kw.lower()
                if k in allowed_kw:
                    continue
                left = r"\b" if k[:1].isalnum() else ""
                right = r"\b" if k[-1:].isalnum() else ""
                if re.search(left + re.escape(k) + right, blob):
                    rep.add("error", qid, "scope.out_of_scope", keyword=kw, chapter=info.get("title", ch))
    return rep
