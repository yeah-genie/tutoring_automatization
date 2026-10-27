# mathcheck — 시험지·퀴즈 검증 도구

학생에게 문제를 내기 전에 네 가지를 자동으로 검사한다. 하나라도 걸리면 "실패"로 나오고, 그 PDF는 내면 안 된다.

| 검사 | 무엇을 잡나 |
|---|---|
| 수학 정답 | 문제 조건만으로 sympy가 다시 푼 값 ≠ 정답, 해설지에 인쇄된 답 ≠ 정답, 반올림 실수, 총점 합 불일치 |
| 인쇄 상태 | LaTeX 컴파일 오류, 오른쪽 여백 넘침, 폰트에 없는 글자, `??` 참조, 잘린 그림, 빈 페이지 |
| 단원 범위 | 고른 단원 밖 개념(예: 이차함수 퀴즈에 미분)이 문제·해설에 쓰임 |
| 중복 | 같은 퀴즈 안 중복 문제, 예전에 낸 문제와 같은 문제 |

## 설치 (내 컴퓨터, 한 번만)

```bash
git clone https://github.com/yeah-genie/tutoring_automatization
cd tutoring_automatization
pip install -r requirements.txt
```
LaTeX(MacTeX 또는 TeX Live)이 설치되어 있어야 한다. `pdflatex --version`으로 확인.

## 명령줄로 쓰기

```bash
mathcheck check examples/sample_quiz.yaml --out build/
```
통과하면 `build/`에 문제지와 해설지 PDF가 생긴다.

## MCP로 연결하기 (Claude가 직접 검사하게)

클로드 코드:
```bash
claude mcp add mathcheck -- python -m mathcheck.server
```
(저장소 폴더 안에서 실행)

Claude 데스크톱 앱: 설정 → 개발자 → 설정 파일 편집
```json
{
  "mcpServers": {
    "mathcheck": {
      "command": "python",
      "args": ["-m", "mathcheck.server"],
      "cwd": "/내/경로/tutoring_automatization"
    }
  }
}
```

연결 후 "이차방정식 복습 퀴즈 4문제 만들어서 mathcheck로 검사해줘"라고 하면, Claude가 퀴즈 사양(YAML)을 쓰고 `check_quiz`를 불러 오류가 없어질 때까지 고친다.

도구 목록: `check_quiz`, `check_math_only`, `check_answer`, `check_latex_file`, `check_scope_only`, `list_chapters`

## 퀴즈 사양 쓰는 법

`docs/quiz_spec_guide.md`와 `examples/sample_quiz.yaml` 참고. 핵심 규칙:
- `check` 코드는 **문제에 적힌 조건만** 써서 답을 계산한다. 정답을 그대로 적어 넣으면 검사 의미가 없다.
- 소수 답은 `tolerance`(허용 오차)나 `sf`(유효숫자)를 적는다.
- 학생 이름 같은 개인정보는 이 공개 저장소에 올리지 않는다.

## 테스트

```bash
python tests/test_mathcheck.py
```
일부러 넣은 오류(틀린 정답, 해설 오타, 반올림 실수, 범위 밖 개념, LaTeX 오류, 여백 넘침, 중복, 총점 불일치)를 모두 잡는지 확인한다.

## 한계

- 단원 범위 검사는 키워드 기반이라 놓치는 경우가 있다. `mathcheck/curricula/*.yaml`에 키워드를 계속 추가한다.
- `check` 코드도 사람이 아닌 AI가 쓰므로, 문제 해석 자체가 틀리면 둘 다 같이 틀릴 수 있다. 그래서 페이지 이미지를 눈으로 한 번 보는 단계는 남겨 둔다.
