"""전체 검사: 사양 형식 → 수학 정답 → 단원 범위 → 중복 → LaTeX 컴파일·인쇄 검사.

하나라도 '오류'가 있으면 ok=False. 이 경우 PDF를 학생에게 보내면 안 된다.
"""
from __future__ import annotations

from pathlib import Path

from .build import write_tex_pair
from .dupes import check_duplicates
from .latex_check import check_tex
from .scope_check import check_scope
from .spec import Report, load_spec, validate_spec
from .verify_math import verify_spec_math


def check_all(spec_path: str | Path, outdir: str | Path, bank_path: str | Path | None = None) -> tuple[Report, dict]:
    spec = load_spec(spec_path)
    rep = validate_spec(spec)
    files: dict = {}
    if not rep.ok:
        return rep, files
    rep.extend(verify_spec_math(spec))
    rep.extend(check_scope(spec))
    rep.extend(check_duplicates(spec, bank_path))
    stem = Path(spec_path).stem
    qp, sol = write_tex_pair(spec, outdir, stem)
    for key, tex in (("question_paper", qp), ("solutions", sol)):
        r, pdf, pages = check_tex(tex)
        rep.extend(r)
        files[key] = {"tex": str(tex), "pdf": str(pdf) if pdf else None, "pages": [str(p) for p in pages]}
    return rep, files
