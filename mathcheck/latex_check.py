"""Print checks: actually compile the LaTeX, read the log, and look at the rendered pages.

Catches
  - compile errors, undefined commands, characters missing from the font
  - undefined references (printed as ??)
  - lines running into the right margin (Overfull hbox above a threshold)
  - text or figures running off the page (ink inside the edge bands of the page image)
  - blank pages
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from .spec import Report

OVERFULL_PT = 5.0
MARGIN_PX = 12  # about 2 mm at 150 dpi


def compile_tex(tex_path: str | Path, timeout: int = 120) -> tuple[Path | None, str | None]:
    """Returns (pdf or None, log text). log is None when pdflatex is missing."""
    tex_path = Path(tex_path)
    if not shutil.which("pdflatex"):
        return None, None
    log = ""
    for _ in range(2):  # second pass fixes page counts and references
        p = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "-no-shell-escape", tex_path.name],
            cwd=tex_path.parent, capture_output=True, text=True, timeout=timeout,
        )
        log_file = tex_path.with_suffix(".log")
        log = log_file.read_text(errors="replace") if log_file.exists() else p.stdout
        if p.returncode != 0:
            return None, log
    pdf = tex_path.with_suffix(".pdf")
    return (pdf if pdf.exists() else None), log


def parse_log(log: str, where: str, overfull_pt: float = OVERFULL_PT) -> Report:
    rep = Report()
    for m in re.finditer(r"^! (.+)$", log, re.M):
        rep.add("error", where, "latex.compile_error", detail=m.group(1).strip())
    for m in re.finditer(r"Overfull \\hbox \(([\d.]+)pt too wide\)[^\n]*lines? (\d+)", log):
        if float(m.group(1)) > overfull_pt:
            rep.add("error", where, "latex.overfull", line=m.group(2), pt=m.group(1))
    for m in re.finditer(r"Missing character: There is no (.+?) in font", log):
        rep.add("error", where, "latex.missing_char", char=m.group(1))
    if re.search(r"There were undefined references|Reference `[^']+' on page \d+ undefined", log):
        rep.add("error", where, "latex.undefined_ref")
    if "Label(s) may have changed" in log:
        rep.add("warning", where, "latex.labels_changed")
    return rep


def render_pages(pdf: Path, dpi: int = 150) -> list[Path]:
    if not shutil.which("pdftoppm"):
        return []
    prefix = pdf.with_suffix("")
    for old in pdf.parent.glob(prefix.name + "_p*.png"):
        old.unlink()
    subprocess.run(["pdftoppm", "-r", str(dpi), "-png", str(pdf), str(prefix) + "_p"], check=True)
    return sorted(pdf.parent.glob(prefix.name + "_p*.png"))


def check_page_images(pages: list[Path], where: str) -> Report:
    rep = Report()
    try:
        from PIL import Image
    except ImportError:
        rep.add("warning", where, "latex.no_pillow")
        return rep
    for i, png in enumerate(pages, 1):
        im = Image.open(png).convert("L")
        w, h = im.size
        px = im.load()

        def ink(box) -> int:
            x0, y0, x1, y1 = box
            return sum(1 for xx in range(x0, x1, 2) for yy in range(y0, y1, 2) if px[xx, yy] < 128)

        if ink((0, 0, w, h)) < 50:
            rep.add("error", where, "latex.blank_page", page=i)
        for side, box in {
            "left": (0, 0, MARGIN_PX, h),
            "right": (w - MARGIN_PX, 0, w, h),
            "top": (0, 0, w, MARGIN_PX),
        }.items():
            if ink(box) > 3:
                rep.add("error", where, "latex.clipped", page=i, side=side)
    rep.info(where, "latex.pages_rendered", n=len(pages))
    return rep


def check_tex(tex_path: str | Path) -> tuple[Report, Path | None, list[Path]]:
    tex_path = Path(tex_path)
    where = tex_path.name
    pdf, log = compile_tex(tex_path)
    if log is None:
        rep = Report()
        rep.add("error", where, "latex.no_pdflatex")
        return rep, None, []
    rep = parse_log(log, where)
    if pdf is None:
        if rep.ok:
            rep.add("error", where, "latex.no_pdf")
        return rep, None, []
    pages = render_pages(pdf)
    if not pages:
        rep.add("warning", where, "latex.no_pdftoppm")
    rep.extend(check_page_images(pages, where))
    return rep, pdf, pages
