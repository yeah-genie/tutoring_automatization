---
name: worksheet-check
description: Check a maths worksheet, test or answer key for wrong answers, bad rounding, out-of-syllabus questions (IGCSE, IB, AP, A-Level), marks that don't add up and unclear wording. Use when a teacher or tutor uploads a worksheet or asks to check, proofread or verify maths questions or an answer key.
---

# Worksheet check

Help teachers find mistakes before students see them. Work in the teacher's language.

## Steps

1. **Read all questions and the answer key.**
   - Include sub-parts such as 3(a) and 3(b).
   - Name any unreadable questions instead of guessing their numbers.

2. **Pick the syllabus if one applies.**
   - Codes: igcse_0580, ib_aa, ib_ai, ap_calculus, ap_precalculus, ap_statistics, caie_9709.
   - Use the course the teacher named. If they didn't name one, infer it from the header and say what you assumed.
   - To see a course's chapters:
     ```bash
     python -c "import sys; sys.path.insert(0,'scripts'); import mathcheck_lite as mc; import json; print(json.dumps({k:v['title'] for k,v in mc.load_curricula()['ib_aa']['chapters'].items()}, indent=1))"
     ```

3. **Solve each question two ways.**
   - (a) Reason it through step by step.
   - (b) Write sympy code that computes the answer from the question's conditions only and sets `result`. Never copy the key into the code.
   - Answer types:
     - Several answers in any order: use a list.
     - Coordinates or other ordered answers: use a tuple.
   - Options:
     - `sf` or `dp` for rounding instructions.
     - `tolerance` for answers read off a graph.

4. **Run the checker.** Write a small script next to `scripts/mathcheck_lite.py`:
   ```python
   import sys; sys.path.insert(0, "scripts")  # path relative to this skill folder
   import mathcheck_lite as mc
   questions = [{"id": "1", "marks": 3, "text": "...", "check": "result = ...", "answer_key": "...", "notes": ""}]
   rep = mc.check_worksheet(questions, curriculum="ib_aa", chapters=["calculus"], total_marks=20)
   print(mc.format_report(rep, lang="en"))
   ```
   - x, y, z, t, n, k, a, b, c are predefined sympy symbols.
   - If a question returns `check_failed`, fix the code and run again.

5. **Confirm every `wrong_key` before reporting it.** Your reasoning in 3(a) must agree with the code.
   - If they disagree, re-read the question.
   - If it is still unresolved, report it as "Needs a look" with both values.

6. **Add suggestions the code can't detect.** Keep each to one line. Look for:
   - missing or contradictory data
   - a diagram that doesn't match the text
   - ambiguous wording
   - rounding that conflicts with the key
   - missing units
   - impossible values
   - typos

7. **"Show that" questions and proofs.** Check the final values. Mark the reasoning "Manual review".

## Report

Give the report in this order:
1. One-line summary.
2. A table of problems only: Question | Problem | Key says | Correct | Why.
3. The full corrected answer key, with changed lines marked.
4. Suggestions.
5. The assumed syllabus and any questions that couldn't be checked.

Keep it short and don't show code unless asked.

Never call a question correct unless the checker returned `ok`.
Don't repeat student names or other personal data.
