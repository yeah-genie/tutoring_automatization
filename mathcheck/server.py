"""mathcheck MCP server.

After an AI assistant writes a quiz or exam paper, it calls these tools to check its own work
before anything reaches a student.

Connect (Claude Code):   claude mcp add mathcheck -- python -m mathcheck.server
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .latex_check import check_tex
from .pipeline import check_spec
from .scope_check import check_scope, list_curricula, load_curriculum
from .spec import Report, load_spec, parse_spec
from .verify_math import check_answer as _check_answer
from .verify_math import verify_spec_math

mcp = FastMCP("mathcheck")


def _load(spec_path: str, spec_yaml: str) -> tuple[dict | None, str, Report | None]:
    try:
        if spec_yaml.strip():
            return parse_spec(spec_yaml), "quiz", None
        return load_spec(spec_path), Path(spec_path).stem, None
    except Exception as e:  # noqa: BLE001
        rep = Report()
        rep.add("error", "spec", "spec.unreadable", detail=e)
        return None, "", rep


@mcp.tool()
def check_quiz(spec_path: str = "", spec_yaml: str = "", outdir: str = "", bank_path: str = "", lang: str = "") -> dict:
    """Full check of a quiz spec: answers re-computed with sympy, printed answers, total marks,
    syllabus scope, duplicates, LaTeX compile and page images.
    Pass either spec_path (a YAML file) or spec_yaml (the YAML text itself).
    If ok is false the quiz must not be handed out: fix each issue and call again.
    On success, files lists the question paper and solutions PDFs and page PNGs: look at the PNGs too."""
    spec, stem, err = _load(spec_path, spec_yaml)
    if err:
        return err.to_dict(lang or None)
    outdir = outdir or tempfile.mkdtemp(prefix="mathcheck_")
    rep, files = check_spec(spec, outdir, stem, bank_path or None)
    return {**rep.to_dict(lang or None), "files": files}


@mcp.tool()
def check_math_only(spec_path: str = "", spec_yaml: str = "", lang: str = "") -> dict:
    """Check only the answers of a quiz spec (fast, no PDF)."""
    spec, _, err = _load(spec_path, spec_yaml)
    return (err or verify_spec_math(spec)).to_dict(lang or None)


@mcp.tool()
def check_answer(problem_code: str, claimed_answer: str, tolerance: float = 0.0, lang: str = "") -> dict:
    """Re-solve one problem with sympy and compare with a claimed answer.
    problem_code: Python using only the problem's conditions; must set `result`.
    claimed_answer: e.g. "12", "sqrt(2)/2", "[2, -5]".
    tolerance: allowed absolute error for decimal answers (0 = exact)."""
    return _check_answer(problem_code, claimed_answer, tolerance or None).to_dict(lang or None)


@mcp.tool()
def check_latex_file(tex_path: str, lang: str = "") -> dict:
    """Compile an existing .tex file and report print problems (compile errors, overfull lines,
    missing glyphs, clipped figures, blank pages)."""
    rep, pdf, pages = check_tex(Path(tex_path))
    return {**rep.to_dict(lang or None), "pdf": str(pdf) if pdf else None, "pages": [str(p) for p in pages]}


@mcp.tool()
def check_scope_only(spec_path: str = "", spec_yaml: str = "", lang: str = "") -> dict:
    """Check whether concepts outside the selected chapters appear in questions or solutions."""
    spec, _, err = _load(spec_path, spec_yaml)
    return (err or check_scope(spec)).to_dict(lang or None)


@mcp.tool()
def list_available_curricula() -> dict:
    """Curriculum codes usable in a spec's `curriculum` field (e.g. igcse_0580, ib_aa, ap_calculus, caie_9709)."""
    return list_curricula()


@mcp.tool()
def list_chapters(curriculum: str) -> dict:
    """Chapter codes and titles of a curriculum; use these codes in the spec's `chapters` list."""
    cur = load_curriculum(curriculum)
    return {k: v.get("title", k) for k, v in cur["chapters"].items()}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
