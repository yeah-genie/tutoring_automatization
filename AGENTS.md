# Instructions for AI assistants (ChatGPT, Claude, Gemini, coding agents)

A teacher may give you this repository's URL together with a maths worksheet, test or answer key and
ask you to "check it". This file tells you how. Follow it step by step. Reply in the teacher's language.

Base URL for raw files:
`https://raw.githubusercontent.com/yeah-genie/tutoring_automatization/main`

| File | Use |
|---|---|
| `integrations/engine/mathcheck_lite.py` | single-file checker, needs only sympy |
| `integrations/engine/curricula/<code>.json` | syllabus data: `igcse_0580`, `ib_aa`, `ib_ai`, `ap_calculus`, `ap_precalculus`, `ap_statistics`, `caie_9709` |
| `examples/demo_worksheet.pdf` | test worksheet with 4 planted mistakes (Q2 rounding, Q4 key, Q5 HL-only on SL sheet, total 20 ≠ 19) |

SHA-256 of mathcheck_lite.py: `1f12fd6cc86eebc4c5a98085f1b9caf7e28e0b638157b112abcb12be78628f24`

---

## Task A: check an existing worksheet (most common)

### 1. Read
List every question and sub-part, such as 3(a) and 3(b), together with the answer key if there is one.
If part of the page is unreadable, name those questions. Do not guess numbers.

### 2. Syllabus (optional)
Use the course the teacher named. If they did not name one, infer it from the header and say what you assumed.
Open `integrations/engine/curricula/<code>.json` to see the chapter codes and titles, then choose the chapters the worksheet covers.
Earlier chapters a chapter depends on are allowed automatically.
If the course is not listed, skip this check and say so.

### 3. Solve every question twice
- a) Reason through it step by step, using only the question's conditions.
- b) Write sympy code that computes the answer from those same conditions and sets `result`. Never copy the answer key into the code.
  - Use a **list** for several answers in any order. Use a **tuple** for ordered answers such as coordinates.
  - Note rounding instructions as `sf` (significant figures) or `dp` (decimal places). Use `tolerance` for answers read off graphs.

### 4. Get the checker into your Python sandbox

Pick the first option that works.

1. **Your sandbox has internet** (Claude, Claude Code, most agents):
   ```python
   import urllib.request, json, sys
   B = "https://raw.githubusercontent.com/yeah-genie/tutoring_automatization/main/integrations/engine"
   urllib.request.urlretrieve(B + "/mathcheck_lite.py", "mathcheck_lite.py")
   cur = json.loads(urllib.request.urlopen(B + "/curricula/ib_aa.json").read())
   sys.path.insert(0, "."); import mathcheck_lite as mc
   ```
2. **No internet in the sandbox, but you can browse** (ChatGPT):
   - Open the raw `mathcheck_lite.py` URL and write its exact text to `mathcheck_lite.py` in the sandbox.
   - Check the SHA-256 against the value above. If it does not match, fetch the file again. Do not run a mistyped copy.
   - Open the curriculum JSON the same way and pass it in as a dict (`cur = json.loads("""...""")`).
3. **Neither works**: run each question's sympy code directly and compare it with the key yourself, using the same rules:
   - exact symbolic equality, or
   - round the computed value to the stated sf/dp before comparing.

   Tell the teacher the syllabus check was skipped.

### 5. Run the checker
```python
questions = [
  {"id": "1", "marks": 3, "text": "Given f(x) = 3x^4 - 5x^2 + 2x, find f'(x).",
   "check": "result = diff(3*x**4 - 5*x**2 + 2*x, x)", "answer_key": "12x^3 - 10x + 2"},
  {"id": "2", "marks": 3, "text": "Solve 2^(x+1) = 48.", "sf": 3,
   "check": "result = solve(Eq(2**(x+1), 48), x)[0]", "answer_key": "x = 4.59"},
]
rep = mc.check_worksheet(questions, curriculum=cur, chapters=["calculus"], total_marks=20)
print(mc.format_report(rep, lang="en"))   # lang="ko" for Korean
```
- `x y z t n k a b c` are predefined sympy symbols, and all sympy functions are available.
- Each question gets one of these verdicts:

| Verdict | Meaning | What you do |
|---|---|---|
| `ok` | The computed answer matches the key | Nothing |
| `wrong_key` | The computed answer does not match the key | Go to step 6 before reporting it |
| `no_key` | There was no answer key | Report the computed value |
| `check_failed` | Your code did not run | Fix the code and run again. Never report this question as correct |

### 6. Confirm before you accuse
Report `wrong_key` only if your step-3a reasoning agrees with the code.
If they disagree, re-read the question.
If it is still unresolved, report the question as **"Needs a look"** and give both values.

### 7. Things code can't see (suggestions, one line each)
- missing or contradictory data
- a diagram that disagrees with the text
- ambiguous wording
- a rounding instruction that conflicts with the key
- missing units
- impossible values
- typos
- odd mark allocations

For "show that" questions, proofs and sketches, check any final values with code and mark the reasoning "Manual review".

### 8. Report (short; teachers read this between lessons)
1. One line, e.g. "12 questions: 2 answer-key errors, 1 out of syllabus, 1 needs a look."
2. A table of **problems only**: Question | Problem | Key says | Correct | Why (one line).
3. The full corrected answer key, with changed lines marked.
4. Suggestions.
5. The syllabus you assumed, and any questions you could not check.

Do not show code unless asked.
Never call a question correct unless it was checked.
Do not repeat student names or other personal data.

---

## Task B: make a new quiz with full print checks (needs Python + LaTeX, e.g. Claude Code)

```bash
pip install git+https://github.com/yeah-genie/tutoring_automatization
mathcheck curricula                 # list syllabus codes
mathcheck chapters ib_aa            # chapter codes
mathcheck check quiz.yaml --out build/   # exit 0 = pass
```
- Spec format: `examples/sample_quiz.yaml` and `docs/quiz_spec_guide.md`.
- The MCP server is `mathcheck-mcp` and exposes the tools `check_quiz` and `check_answer`.
- Iterate until the check passes, then look at the page PNGs in `build/`.

## Repository map
- `mathcheck/` — full package: answer verification, LaTeX build and print checks, scope, duplicates, MCP server
- `mathcheck/curricula/*.yaml` — syllabus source files. After editing them, run `python tools/build_integrations.py` to regenerate the JSON.
- `integrations/` — no-install engine, ChatGPT GPT setup, Claude skill
- `workflows/tutoring/` — the author's own homework-grading automation (Korean); not needed for the tasks above
- `tests/` — `python tests/test_mathcheck.py && python tests/test_lite.py`
