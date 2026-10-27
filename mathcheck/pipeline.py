"""Full check: spec format -> answers -> syllabus scope -> duplicates -> LaTeX compile and page images.

Any error makes ok=False; a failing quiz should not be handed out.
"""
from __future__ import annotations

import re
from pathlib import Path

from .build import write_tex_pair
from .dupes import check_duplicates
from .latex_check import check_tex
from .scope_check import check_scope
from .spec import Report, load_spec, validate_spec
from .verify_math import verify_spec_math


def check_spec(spec: dict, outdir: str | Path, stem: str = "quiz", bank_path: str | Path | None = None,
               build_pdf: bool = True, timeout: int = 20) -> tuple[Report, dict]:
    rep = validate_spec(spec)
    files: dict = {}
    if not rep.ok:
        return rep, files
    rep.extend(verify_spec_math(spec, timeout=timeout))
    rep.extend(check_scope(spec))
    rep.extend(check_duplicates(spec, bank_path))
    if not build_pdf:
        return rep, files
    stem = re.sub(r"[^\w.-]+", "_", stem) or "quiz"
    qp, sol = write_tex_pair(spec, outdir, stem)
    for key, tex in (("question_paper", qp), ("solutions", sol)):
        r, pdf, pages = check_tex(tex)
        rep.extend(r)
        files[key] = {"tex": str(tex), "pdf": str(pdf) if pdf else None, "pages": [str(p) for p in pages]}
    return rep, files


def check_all(spec_path: str | Path, outdir: str | Path, bank_path: str | Path | None = None,
              build_pdf: bool = True) -> tuple[Report, dict]:
    try:
        spec = load_spec(spec_path)
    except Exception as e:  # noqa: BLE001
        rep = Report()
        rep.add("error", "spec", "spec.unreadable", detail=e)
        return rep, {}
    return check_spec(spec, outdir, Path(spec_path).stem, bank_path, build_pdf)
