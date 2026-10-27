"""퀴즈 사양 → 문제지/해설지 LaTeX 생성.

레이아웃은 Cambridge IGCSE 기출 형식을 단순화한 것:
수험자 정보 박스, INSTRUCTIONS, 문항 번호와 오른쪽 [배점], 점선 풀이 공간.
해설지는 문항마다 최종 답 + 단계별 풀이(worked solutions).
"""
from __future__ import annotations

from pathlib import Path

PREAMBLE = r"""\documentclass[11pt,a4paper]{article}
\usepackage[margin=20mm]{geometry}
\usepackage{amsmath,amssymb}
\usepackage{tikz,pgfplots}
\pgfplotsset{compat=1.18}
\usepackage{enumitem}
\usepackage{lastpage}
\usepackage{fancyhdr}
\pagestyle{fancy}\fancyhf{}
\cfoot{\small Page \thepage\ of \pageref{LastPage}}
\renewcommand{\headrulewidth}{0pt}
\setlength{\parindent}{0pt}
\newcommand{\qmarks}[1]{\hfill\textbf{[#1]}}
\newcommand{\answerlines}[1]{\par\foreach \i in {1,...,#1}{\vspace{6mm}\noindent\makebox[\linewidth]{\dotfill}\par}}
\begin{document}
"""


def _header(spec: dict, solutions: bool) -> str:
    title = spec["title"] + (" --- Worked Solutions" if solutions else "")
    total = sum(int(q["marks"]) for q in spec["questions"])
    box = "" if solutions else (
        r"\noindent\fbox{\parbox{\dimexpr\linewidth-2\fboxsep-2\fboxrule\relax}{\vspace{2mm}"
        r"CANDIDATE NAME \dotfill\ \hspace{4mm} DATE \dotfill\vspace{2mm}}}\par\vspace{4mm}" "\n\n"
    )
    instr = "" if solutions else (
        r"\textbf{INSTRUCTIONS}\begin{itemize}[nosep]"
        r"\item Answer \textbf{all} questions."
        r"\item Show all necessary working clearly."
        r"\item Give non-exact numerical answers correct to 3 significant figures, or 1 decimal place for angles in degrees, unless the question says otherwise."
        r"\end{itemize}"
        rf"\textbf{{INFORMATION}}\begin{{itemize}}[nosep]\item The total mark for this paper is {total}.\end{{itemize}}"
        "\n"
    )
    return rf"{{\Large\bfseries {title}}}\par\vspace{{3mm}}" "\n" + box + instr + r"\vspace{4mm}\hrule\vspace{4mm}" "\n"


def build_tex(spec: dict, solutions: bool = False) -> str:
    parts = [PREAMBLE, _header(spec, solutions)]
    for q in spec["questions"]:
        parts.append(rf"\textbf{{{q['id']}}}\quad " + q["text"].strip())
        if q.get("diagram"):
            parts.append("\n\\begin{center}\n" + q["diagram"].strip() + "\n\\end{center}\n")
        if solutions:
            parts.append(r"\par\vspace{2mm}\textbf{Answer:} " + str(q["final_answer"]))
            parts.append(r"\par\vspace{1mm}" + q["solution"].strip())
            if q.get("trap"):
                parts.append(r"\par\vspace{1mm}\emph{Common mistake:} " + q["trap"].strip())
            parts.append(rf"\qmarks{{{q['marks']}}}")
        else:
            lines = q.get("answer_lines", max(3, 2 * int(q["marks"])))
            parts.append(rf"\qmarks{{{q['marks']}}}\answerlines{{{lines}}}")
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
