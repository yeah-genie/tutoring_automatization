"""Message catalog. Every issue has a stable `code`; the human message is rendered here.

Language: argument > MATHCHECK_LANG env var > "en".
To add a language, add a column to MESSAGES (missing keys fall back to English).
"""
from __future__ import annotations

import os

MESSAGES: dict[str, dict[str, str]] = {
    # report
    "report.pass": {"en": "PASS", "ko": "통과"},
    "report.fail": {"en": "FAIL (do not hand this out)", "ko": "실패 (학생에게 내면 안 됨)"},
    "report.head": {"en": "Check result: {status}", "ko": "검사 결과: {status}"},
    "level.error": {"en": "error", "ko": "오류"},
    "level.warning": {"en": "warning", "ko": "주의"},
    "level.info": {"en": "info", "ko": "참고"},
    # spec
    "spec.missing_key": {"en": "missing top-level key '{key}'", "ko": "'{key}' 항목이 없음"},
    "spec.no_questions": {"en": "no questions", "ko": "문항이 하나도 없음"},
    "spec.empty_field": {"en": "field '{key}' is missing or empty", "ko": "'{key}' 항목이 비어 있음"},
    "spec.duplicate_id": {"en": "duplicate question id", "ko": "문항 번호가 중복됨"},
    "spec.bad_marks": {"en": "marks must be a positive integer", "ko": "배점(marks)은 1 이상의 정수여야 함"},
    "spec.unreadable": {"en": "could not read spec: {detail}", "ko": "사양을 읽을 수 없음: {detail}"},
    # math
    "math.no_result": {"en": "check code did not set a `result` variable", "ko": "check 코드에 result 변수가 없음"},
    "math.timeout": {"en": "check code did not finish within {timeout}s", "ko": "check 코드가 {timeout}초 안에 끝나지 않음"},
    "math.runtime_error": {"en": "check code raised: {detail}", "ko": "check 코드 실행 오류: {detail}"},
    "math.bad_output": {"en": "check code produced unreadable output", "ko": "check 코드 출력 형식 오류"},
    "math.blocked": {"en": "check code not allowed: {detail}", "ko": "허용되지 않는 check 코드: {detail}"},
    "math.bad_expected": {"en": "cannot parse `expected`: {detail}", "ko": "expected를 식으로 읽을 수 없음: {detail}"},
    "math.mismatch": {
        "en": "computed {computed} != expected {expected}; the answer or the question's conditions may be wrong",
        "ko": "계산 결과 {computed} ≠ 정답 {expected}. 정답이나 문제 조건이 틀렸을 수 있음",
    },
    "math.printed_missing": {
        "en": "printed final answer '{final}' does not show the expected value {target}",
        "ko": "해설지 최종 답 '{final}'에 정답 {target}이(가) 보이지 않음",
    },
    "math.verified": {"en": "answer verified: {expected}", "ko": "정답 확인: {expected}"},
    "math.total_mismatch": {
        "en": "declared total_marks {declared} != sum of question marks {total}",
        "ko": "표지에 적힌 총점 {declared} ≠ 문항 배점 합 {total}",
    },
    "math.claim_ok": {"en": "matches: {computed}", "ko": "일치: {computed}"},
    "math.claim_mismatch": {"en": "computed {computed} != claimed {claimed}", "ko": "계산 결과 {computed} ≠ 주장한 답 {claimed}"},
    # latex
    "latex.no_pdflatex": {"en": "pdflatex is not installed", "ko": "pdflatex가 설치되어 있지 않음"},
    "latex.compile_error": {"en": "compile error: {detail}", "ko": "컴파일 오류: {detail}"},
    "latex.overfull": {
        "en": "text near line {line} runs {pt}pt into the right margin",
        "ko": "{line}번째 줄 근처가 오른쪽 여백을 {pt}pt 넘음",
    },
    "latex.missing_char": {"en": "character missing from font: {char}", "ko": "폰트에 없는 글자가 빠짐: {char}"},
    "latex.undefined_ref": {"en": "undefined references (shown as ?? in the PDF)", "ko": "정의되지 않은 참조가 있음 (PDF에 ??로 보임)"},
    "latex.labels_changed": {"en": "labels may have changed", "ko": "참조 번호가 바뀌었을 수 있음"},
    "latex.no_pdf": {"en": "no PDF was produced", "ko": "PDF가 만들어지지 않음"},
    "latex.no_pillow": {"en": "Pillow not installed; page image checks skipped", "ko": "Pillow가 없어 페이지 이미지 검사를 건너뜀"},
    "latex.no_pdftoppm": {"en": "pdftoppm not installed; page image checks skipped", "ko": "pdftoppm이 없어 페이지 이미지 검사를 건너뜀"},
    "latex.blank_page": {"en": "page {page} is blank", "ko": "{page}쪽이 비어 있음"},
    "latex.clipped": {"en": "page {page}: ink touches the {side} edge (clipped text or figure)", "ko": "{page}쪽 {side} 끝에 글자나 그림이 잘려 나감"},
    "latex.pages_rendered": {"en": "{n} page image(s) rendered; look at them once", "ko": "{n}쪽 이미지 생성 (눈으로 한 번 더 확인 권장)"},
    "side.left": {"en": "left", "ko": "왼쪽"},
    "side.right": {"en": "right", "ko": "오른쪽"},
    "side.top": {"en": "top", "ko": "위"},
    # scope
    "scope.no_curriculum": {"en": "curriculum '{name}' not found; scope check skipped", "ko": "단원 정보 '{name}'이(가) 없어 범위 검사를 건너뜀"},
    "scope.unknown_chapter": {"en": "chapter '{chapter}' is not in curriculum {curriculum}", "ko": "단원 '{chapter}'이(가) {curriculum} 단원 목록에 없음"},
    "scope.out_of_scope": {
        "en": "out-of-scope concept '{keyword}' (chapter: {chapter})",
        "ko": "범위 밖 개념 '{keyword}' ({chapter} 단원)이 쓰임",
    },
    # duplicates
    "dup.within": {"en": "same question as {other}", "ko": "{other}와(과) 같은 문제"},
    "dup.bank": {"en": "same as a question already used on {date}", "ko": "{date}에 낸 적 있는 문제와 같음"},
}


def resolve_lang(lang: str | None = None) -> str:
    lang = (lang or os.environ.get("MATHCHECK_LANG") or "en").lower()[:2]
    return lang


def t(code: str, lang: str | None = None, **params) -> str:
    row = MESSAGES.get(code)
    if row is None:
        return code + (" " + str(params) if params else "")
    template = row.get(resolve_lang(lang)) or row["en"]
    if "side" in params and f"side.{params['side']}" in MESSAGES:
        params = {**params, "side": t(f"side.{params['side']}", lang)}
    try:
        return template.format(**params)
    except (KeyError, IndexError):
        return template
