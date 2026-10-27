"""mathcheck MCP 서버.

Claude(클로드 코드·데스크톱)가 시험지나 퀴즈를 만든 뒤 이 도구들을 불러 스스로 검사한다.

연결 (클로드 코드):
  claude mcp add mathcheck -- python -m mathcheck.server
  (저장소 폴더에서 실행하거나, PYTHONPATH에 저장소 경로를 넣는다)
"""
from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .latex_check import check_tex
from .pipeline import check_all
from .scope_check import check_scope, load_curriculum
from .spec import load_spec
from .verify_math import check_answer as _check_answer
from .verify_math import verify_spec_math

mcp = FastMCP("mathcheck")


@mcp.tool()
def check_quiz(spec_path: str, outdir: str = "build", bank_path: str = "") -> dict:
    """퀴즈 사양(YAML) 전체 검사: 수학 정답, 단원 범위, 중복, LaTeX 컴파일과 인쇄 상태.
    ok가 false면 학생에게 내면 안 된다. issues를 하나씩 고치고 다시 호출할 것.
    통과하면 files에 문제지·해설지 PDF와 페이지 이미지 경로가 있다. 이미지를 열어 눈으로도 확인할 것."""
    rep, files = check_all(spec_path, outdir, bank_path or None)
    return {**rep.to_dict(), "files": files}


@mcp.tool()
def check_math_only(spec_path: str) -> dict:
    """퀴즈 사양의 수학 정답만 빠르게 검사한다 (PDF는 만들지 않음)."""
    return verify_spec_math(load_spec(spec_path)).to_dict()


@mcp.tool()
def check_answer(problem_code: str, claimed_answer: str, tolerance: float = 0.0) -> dict:
    """문제 하나를 sympy 코드로 다시 풀어 주장한 답과 비교한다.
    problem_code: 문제 조건만으로 답을 계산하고 마지막에 result 변수에 넣는 파이썬 코드.
    claimed_answer: 확인할 답 (예: "12", "sqrt(2)/2", "[2, -5]").
    tolerance: 소수 답 허용 오차 (0이면 정확히 같아야 함)."""
    return _check_answer(problem_code, claimed_answer, tolerance or None).to_dict()


@mcp.tool()
def check_latex_file(tex_path: str) -> dict:
    """이미 있는 .tex 파일을 컴파일해 인쇄 오류(컴파일 오류, 여백 넘침, 빠진 글자, 잘린 그림, 빈 페이지)를 검사한다."""
    rep, pdf, pages = check_tex(Path(tex_path))
    return {**rep.to_dict(), "pdf": str(pdf) if pdf else None, "pages": [str(p) for p in pages]}


@mcp.tool()
def check_scope_only(spec_path: str) -> dict:
    """정해진 단원 범위 밖 개념이 문제나 해설에 쓰였는지 검사한다."""
    return check_scope(load_spec(spec_path)).to_dict()


@mcp.tool()
def list_chapters(curriculum: str = "igcse_0580") -> dict:
    """교육과정의 단원 코드와 제목 목록. 퀴즈 사양의 chapters에 이 코드를 쓴다."""
    cur = load_curriculum(curriculum)
    return {k: v.get("title", k) for k, v in cur["chapters"].items()}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
