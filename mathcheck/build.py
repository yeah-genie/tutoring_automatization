"""Quiz spec -> question paper and worked-solutions LaTeX.

Default layout is a simplified exam paper: candidate box, instructions, numbered questions with
[marks] on the right, dotted answer lines. Everything visible can be changed in the spec's
optional `layout:` block (see docs/spec-format.md):

layout:
  paper: a4paper            # or letterpaper
  font_size: 11             # 10, 11 or 12
  margin_mm: 20
  candidate_box: true
  instructions: [...]       # replaces the default instruction bullets; [] removes the block
  show_total: true
  answer_lines: true        # dotted lines on the question paper
  labels: {answer: "Answer:", common_mistake: "Common mistake:", solutions_suffix: " --- Worked Solutions",
           page: "Page {page} of {pages}", candidate: "CANDIDATE NAME", date: "DATE",
           instructions: "INSTRUCTIONS", information: "INFORMATION", total: "The total mark for this paper is {total}."}
  preamble_extra: |         # extra LaTeX packages, e.g. \\usepackage{kotex} for Korean text
    \\usepackage{kotex}
"""
from __future__ import annotations

from pathlib import Path

DEFAULT_INSTRUCTIONS = [
    r"Answer \textbf{all} questions.",
    r"Show all necessary working clearly.",
    r"Give non-exact numerical answers correct to 3 significant figures, or 1 decimal place for angles "
    r"in degrees, unless the question says otherwise.",
]

DEFAULT_LABELS = {
    "answer": "Answer:",
    "common_mistake": "Common mistake:",
    "solutions_suffix": " --- Worked Solutions",
    "page": r"Page {page} of {pages}",
    "candidate": "CANDIDATE NAME",
    "date": "DATE",
    "instructions": "INSTRUCTIONS",
    "information": "INFORMATION",
    "total": "The total mark for this paper is {total}.",
}


def _layout(spec: dict) -> dict:
    lay = dict(spec.get("layout") or {})
    lay.setdefault("paper", "a4paper")
    lay.setdefault("font_size", 11)
    lay.setdefault("margin_mm", 20)
    lay.setdefault("candidate_box", True)
    lay.setdefault("instructions", DEFAULT_INSTRUCTIONS)
    lay.setdefault("show_total", True)
    lay.setdefault("answer_lines", True)
    lay["labels"] = {**DEFAULT_LABELS, **(lay.get("labels") or {})}
    return lay


def _preamble(lay: dict) -> str:
    page = lay["labels"]["page"].replace("{page}", r"\thepage").replace("{pages}", r"\pageref{LastPage}")
    return (
        rf"\documentclass[{int(lay['font_size'])}pt,{lay['paper']}]{{article}}" "\n"
        rf"\usepackage[margin={float(lay['margin_mm'])}mm]{{geometry}}" "\n"
        r"""\usepackage{amsmath,amssymb}
\usepackage{tikz,pgfplots}
\pgfplotsset{compat=1.18}
\usepackage{enumitem}
\usepackage{lastpage}
\usepackage{fancyhdr}
\pagestyle{fancy}\fancyhf{}
\renewcommand{\headrulewidth}{0pt}
\setlength{\parindent}{0pt}
\newcommand{\qmarks}[1]{\hfill\textbf{[#1]}}
\newcommand{\answerlines}[1]{\par\foreach \i in {1,...,#1}{\vspace{6mm}\noindent\makebox[\linewidth]{\dotfill}\par}}
"""
        + rf"\cfoot{{\small {page}}}" "\n"
        + (str(lay.get("preamble_extra") or "").strip() + "\n")
        + r"\begin{document}" "\n"
    )


def _header(spec: dict, lay: dict, solutions: bool) -> str:
    lab = lay["labels"]
    title = spec["title"] + (lab["solutions_suffix"] if solutions else "")
    total = sum(int(q["marks"]) for q in spec["questions"])
    out = rf"{{\Large\bfseries {title}}}\par\vspace{{3mm}}" "\n"
    if solutions:
        return out + r"\vspace{4mm}\hrule\vspace{4mm}" "\n"
    if lay["candidate_box"]:
        out += (
            r"\noindent\fbox{\parbox{\dimexpr\linewidth-2\fboxsep-2\fboxrule\relax}{\vspace{2mm}"
            rf"{lab['candidate']} \dotfill\ \hspace{{4mm}} {lab['date']} \dotfill\vspace{{2mm}}}}}}\par\vspace{{4mm}}"
            "\n\n"
        )
    if lay["instructions"]:
        items = "".join(rf"\item {i}" for i in lay["instructions"])
        out += rf"\textbf{{{lab['instructions']}}}\begin{{itemize}}[nosep]{items}\end{{itemize}}" "\n"
    if lay["show_total"]:
        out += (
            rf"\textbf{{{lab['information']}}}\begin{{itemize}}[nosep]\item {lab['total'].format(total=total)}"
            r"\end{itemize}" "\n"
        )
    return out + r"\vspace{4mm}\hrule\vspace{4mm}" "\n"


def build_tex(spec: dict, solutions: bool = False) -> str:
    lay = _layout(spec)
    lab = lay["labels"]
    parts = [_preamble(lay), _header(spec, lay, solutions)]
    for q in spec["questions"]:
        parts.append(rf"\textbf{{{q['id']}}}\quad " + str(q["text"]).strip())
        if q.get("diagram"):
            parts.append("\n\\begin{center}\n" + str(q["diagram"]).strip() + "\n\\end{center}\n")
        if solutions:
            parts.append(rf"\par\vspace{{2mm}}\textbf{{{lab['answer']}}} " + str(q["final_answer"]))
            parts.append(r"\par\vspace{1mm}" + str(q["solution"]).strip())
            if q.get("trap"):
                parts.append(rf"\par\vspace{{1mm}}\emph{{{lab['common_mistake']}}} " + str(q["trap"]).strip())
            parts.append(rf"\qmarks{{{q['marks']}}}")
        else:
            lines = q.get("answer_lines", max(3, 2 * int(q["marks"]))) if lay["answer_lines"] else 0
            parts.append(rf"\qmarks{{{q['marks']}}}" + (rf"\answerlines{{{int(lines)}}}" if lines else ""))
        parts.append("\n\\vspace{6mm}\n")
    parts.append(r"\end{document}" "\n")
    return "\n".join(parts)


def write_tex_pair(spec: dict, outdir: str | Path, stem: str = "quiz") -> tuple[Path, Path]:
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    qp = outdir / f"{stem}.tex"
    sol = outdir / f"{stem}_solutions.tex"
    qp.write_text(build_tex(spec, solutions=False), encoding="utf-8")
    sol.write_text(build_tex(spec, solutions=True), encoding="utf-8")
    return qp, sol
