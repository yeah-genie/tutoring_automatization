# ChatGPT GPT 만들기 (예진 계정에서 10분)

1. chatgpt.com → 왼쪽 **GPT** → **+ 만들기** → 위쪽 **구성(Configure)** 탭
2. 아래 값을 그대로 붙여넣기

| 항목 | 값 |
|---|---|
| 이름 | Worksheet Checker — Maths (IB · AP · IGCSE · A-Level) |
| 설명 | Unofficial helper. Upload a maths worksheet or answer key. Finds wrong answers, rounding errors, out-of-syllabus questions and marks that don't add up — before your students do. |
| 지침(Instructions) | `instructions.md` 내용 전체 |
| 대화 스타터 1 | Check this worksheet and answer key for mistakes. |
| 대화 스타터 2 | Is everything on this test within IB AA SL? |
| 대화 스타터 3 | 이 문제지 정답지 오류 있는지 검사해줘 |
| 대화 스타터 4 | Check just this one question: |
| 지식(Knowledge) 파일 | `integrations/engine/mathcheck_lite.py`, `integrations/engine/curricula.json` 두 개 업로드 |
| 기능 | **코드 인터프리터 및 데이터 분석: 켜기** (필수). 웹 검색·이미지 생성: 끄기 |

3. 오른쪽 미리보기에 `examples/demo_worksheet.pdf`를 올리고 "check this" → 2번(반올림), 4번(정답 10), 5번(HL 범위), 총점 20≠19 네 개를 잡으면 성공
4. **만들기/공유** → 처음엔 "링크가 있는 사람"으로 지인 선생님 2~3명에게 테스트 → 괜찮으면 "GPT 스토어"로 공개 (스토어 공개는 빌더 프로필 이름 인증 필요)

## 주의
- 지식 파일을 고치면(교육과정 추가 등) GPT에도 다시 업로드해야 반영됨. 파일은 `python tools/build_integrations.py`로 다시 만든다.
- 스토어에 올릴 때 이름에 "IB", "Cambridge" 같은 상표를 공식처럼 쓰지 않도록 설명에 "unofficial" 문구를 유지한다.
