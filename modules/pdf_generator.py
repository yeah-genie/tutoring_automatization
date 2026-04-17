"""
LaTeX 기반 시험지 & 해설지 PDF 생성 모듈
xelatex + exam.cls 사용 — Cambridge / IGCSE 스타일
"""

import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path

import anthropic

import config
from prompts.exam_prompt import (
    EXAM_SYSTEM,
    MARKSCHEME_SYSTEM,
    exam_paper_prompt,
    markscheme_prompt,
)

logger = logging.getLogger(__name__)


class ExamPDFGenerator:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self.output_dir = Path(config.DOWNLOAD_DIR) / "exams"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ── public API ────────────────────────────────────────────────

    def generate(
        self,
        student_name: str,
        unit: str,
        assignments: list[dict],
        level: str = "IGCSE",
    ) -> dict[str, Path]:
        """
        시험지 + 해설지 PDF를 생성하고 경로를 반환한다.
        Returns: {"paper": Path, "markscheme": Path}
        """
        logger.info("시험지 생성 시작 — %s / %s", student_name, unit)

        # 1. 시험지 LaTeX 생성
        paper_latex = self._generate_latex(
            exam_paper_prompt(student_name, unit, assignments, level),
            EXAM_SYSTEM,
            context="question paper",
        )

        # 2. 해설지 LaTeX 생성 (시험지 참조)
        ms_latex = self._generate_latex(
            markscheme_prompt(student_name, unit, paper_latex),
            MARKSCHEME_SYSTEM,
            context="mark scheme",
        )

        # 3. PDF 컴파일
        slug = re.sub(r"[^\w]", "_", f"{student_name}_{unit}")
        paper_pdf = self._compile(paper_latex, f"{slug}_paper")
        ms_pdf = self._compile(ms_latex, f"{slug}_markscheme")

        logger.info("PDF 생성 완료 — %s | %s", paper_pdf, ms_pdf)
        return {"paper": paper_pdf, "markscheme": ms_pdf}

    # ── internals ─────────────────────────────────────────────────

    def _generate_latex(self, prompt: str, system: str, context: str) -> str:
        """Claude로 LaTeX 소스 생성."""
        logger.info("Claude에 %s LaTeX 요청 중...", context)
        resp = self.client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=8000,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        # 코드 펜스 제거 (Claude가 실수로 감쌀 경우)
        raw = re.sub(r"^```(?:latex|tex)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        return raw

    def _compile(self, latex_src: str, stem: str) -> Path:
        """pdflatex 2-pass compile → returns PDF path."""
        # Use a persistent build dir so MiKTeX package cache is reused
        build_dir = self.output_dir / "build" / stem
        build_dir.mkdir(parents=True, exist_ok=True)

        tex_file = build_dir / f"{stem}.tex"
        tex_file.write_text(latex_src, encoding="utf-8")

        cmd = [
            "pdflatex",
            "-interaction=nonstopmode",
            "-output-directory", str(build_dir),
            str(tex_file),
        ]
        for pass_num in range(2):
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=300,  # 5 min — MiKTeX auto-installs packages on first run
            )
            logger.debug("pdflatex pass %d returncode=%d", pass_num + 1, result.returncode)

        pdf_tmp = build_dir / f"{stem}.pdf"
        if not pdf_tmp.exists():
            log_file = build_dir / f"{stem}.log"
            log_tail = log_file.read_text(encoding="utf-8", errors="replace")[-3000:] if log_file.exists() else result.stdout[-3000:]
            raise RuntimeError(f"pdflatex compile failed ({stem}):\n{log_tail}")

        out_pdf = self.output_dir / f"{stem}.pdf"
        import shutil
        shutil.copy2(pdf_tmp, out_pdf)
        return out_pdf
