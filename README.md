# mathcheck

**A second pair of eyes for maths worksheets made with AI.**

AI assistants can write a quiz in seconds, but they also get answers wrong, print a different
answer on the mark scheme, round badly, or slip in a topic your students haven't learned yet.
mathcheck checks every question before you hand it out:

| Check | What it catches |
|---|---|
| Answers | Re-solves each question with a computer algebra system (sympy); flags a wrong answer key, a mark-scheme typo, wrong rounding, marks that don't add up |
| Printing | Compiles the paper and looks at every page: LaTeX errors, text running off the page, missing symbols, `??` references, blank pages |
| Syllabus | Concepts from chapters you didn't select (e.g. calculus in a quadratics quiz), while allowing earlier prerequisite chapters |
| Repeats | The same question twice, or a question you already used |

Curricula included: **IGCSE 0580, IB Maths AA and AI (SL/HL), AP Calculus AB/BC, AP Precalculus, AP Statistics, Cambridge A-Level 9709.** You can add your own.

Messages in English or Korean (`--lang ko`).

> Status: early. Works today for people comfortable installing Python and LaTeX, or using Claude Code.
> A no-install version for teachers is planned.

## Quick start

```bash
pip install git+https://github.com/yeah-genie/tutoring_automatization
mathcheck check examples/sample_quiz.yaml --out build/
```
Needs a LaTeX installation (TeX Live / MacTeX) with `pdflatex` and `pdftoppm` (poppler).

## Use it from Claude

```bash
claude mcp add mathcheck -- mathcheck-mcp
```
Then ask: *"Make a 4-question review quiz on IB AA SL calculus and check it with mathcheck."*
Claude writes the quiz, calls `check_quiz`, and fixes problems until it passes.

## Writing a quiz spec

See [`examples/sample_quiz.yaml`](examples/sample_quiz.yaml) and [`docs/quiz_spec_guide.md`](docs/quiz_spec_guide.md).
Each question carries a short piece of `check` code that solves it from the question's own conditions,
the `expected` answer, and the `final_answer` printed on the mark scheme. All three must agree.

## Safety note

`check` code is run in a separate process with an import allow-list, resource limits and a timeout.
This is a guard rail, not a security sandbox; don't run specs from people you don't trust.

## Also in this repo

`workflows/tutoring/` — the author's own homework-grading automation (Korean), kept as an example of
using mathcheck in a daily tutoring workflow.

License: MIT
