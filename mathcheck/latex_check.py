"""인쇄 오류 검사: LaTeX을 실제로 컴파일하고 로그와 PDF 이미지를 본다.

잡는 것
  - 컴파일 오류, 정의되지 않은 명령, 빠진 글자(폰트에 없는 문자)
  - 정의되지 않은 참조(??로 찍히는 것)
  - 줄이 오른쪽 여백을 넘는 경우(Overfull hbox, 기본 5pt 초과)
  - 페이지 밖으로 나간 그림·글자(여백 띠에 잉크가 있는지 이미지로 확인)
  - 빈 페이지
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from .spec import Report

OVERFULL_PT = 5.0
MARGIN_PX = 12  # 150dpi 기준 약 2mm


def compile_tex(tex_path: str | Path, timeout: int = 120) -> tuple[Path | None, str]:
    tex_path = Path(tex_path)
    if not shutil.which("pdflatex"):
        return None, "pdflatex가 설치되어 있지 않음"
    log = ""
    for _ in range(2):  # 두 번 돌려야 페이지 번호·참조가 맞음
        p = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", tex_path.name],
            cwd=tex_path.parent,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        log_file = tex_path.with_suffix(".log")
        log = log_file.read_text(errors="replace") if log_file.exists() else p.stdout
        if p.returncode != 0:
            return None, log
    pdf = tex_path.with_suffix(".pdf")
    return (pdf if pdf.exists() else None), log


def parse_log(log: str, where: str) -> Report:
    rep = Report()
    for m in re.finditer(r"^! (.+)$", log, re.M):
        rep.add("error", where, f"컴파일 오류: {m.group(1).strip()}")
    for m in re.finditer(r"Overfull \\hbox \(([\d.]+)pt too wide\)[^\n]*lines? (\d+)", log):
        if float(m.group(1)) > OVERFULL_PT:
            rep.add("error", where, f"{m.group(2)}번째 줄 근처가 오른쪽 여백을 {m.group(1)}pt 넘음")
    for m in re.finditer(r"Missing character: There is no (.+?) in font", log):
        rep.add("error", where, f"폰트에 없는 글자가 빠짐: {m.group(1)}")
    if re.search(r"There were undefined references|Reference `[^']+' on page \d+ undefined", log):
        rep.add("error", where, "정의되지 않은 참조가 있음 (PDF에 ??로 보임)")
    if "Label(s) may have changed" in log:
        rep.add("warning", where, "참조 번호가 바뀌었을 수 있음")
    return rep


def render_pages(pdf: Path, dpi: int = 150) -> list[Path]:
    if not shutil.which("pdftoppm"):
        return []
    prefix = pdf.with_suffix("")
    subprocess.run(["pdftoppm", "-r", str(dpi), "-png", str(pdf), str(prefix) + "_p"], check=True)
    return sorted(pdf.parent.glob(prefix.name + "_p*.png"))


def check_page_images(pages: list[Path], where: str) -> Report:
    rep = Report()
    try:
        from PIL import Image
    except ImportError:
        rep.add("warning", where, "Pillow가 없어 페이지 이미지 검사를 건너뜀")
        return rep
    for i, png in enumerate(pages, 1):
        im = Image.open(png).convert("L")
        w, h = im.size
        px = im.load()

        def ink(box) -> int:
            x0, y0, x1, y1 = box
            return sum(1 for xx in range(x0, x1, 2) for yy in range(y0, y1, 2) if px[xx, yy] < 128)

        if ink((0, 0, w, h)) < 50:
            rep.add("error", where, f"{i}쪽이 비어 있음")
        for name, box in {
            "왼쪽": (0, 0, MARGIN_PX, h),
            "오른쪽": (w - MARGIN_PX, 0, w, h),
            "위": (0, 0, w, MARGIN_PX),
        }.items():
            if ink(box) > 3:
                rep.add("error", where, f"{i}쪽 {name} 끝에 글자나 그림이 잘려 나감")
    rep.notes.append(f"{where}: {len(pages)}쪽 이미지 생성 (눈으로 한 번 더 확인 권장)")
    return rep


def check_tex(tex_path: str | Path) -> tuple[Report, Path | None, list[Path]]:
    tex_path = Path(tex_path)
    where = tex_path.name
    pdf, log = compile_tex(tex_path)
    rep = parse_log(log, where)
    if pdf is None:
        if rep.ok:
            rep.add("error", where, "PDF가 만들어지지 않음")
        return rep, None, []
    pages = render_pages(pdf)
    rep.extend(check_page_images(pages, where))
    return rep, pdf, pages
