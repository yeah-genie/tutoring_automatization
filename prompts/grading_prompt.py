"""
Claude API에 전달할 프롬프트 모음.
"""

GRADING_SYSTEM = """당신은 수학 과외 선생님의 숙제 채점 도우미입니다.
학생이 제출한 숙제 사진이나 PDF를 분석하여 정확하고 친절한 피드백을 제공합니다.
반드시 JSON 형식으로만 응답하고, JSON 외 다른 텍스트는 포함하지 마세요."""

def grading_user_prompt(unit_hint: str = "") -> str:
    unit_line = f"\n※ 학생이 입력한 단원명: {unit_hint} (참고용 — 실제 문제 내용과 다르면 문제 기준으로 판단)" if unit_hint else ""
    return f"""다음 숙제 이미지를 분석해서 아래 JSON 형식으로만 응답해주세요.{unit_line}

**분석 항목:**
1. 이미지에 있는 모든 문제를 빠짐없이 찾아주세요 (1번, 2번처럼 큰 번호 아래 소문제 a, b, c, d가 있으면 각각 개별 항목으로 분석)
2. 각 문제마다 학생이 실제로 쓴 답을 읽어주세요
3. 정답과 비교해서 정오 판정
4. 오답이면 오답 유형 분류:
   - "개념부족": 개념 이해 부족으로 인한 오류
   - "계산실수": 계산 과정의 단순 실수
   - "풀이순서": 풀이 방법/순서 오류
   - "문제이해": 문제 해석 오류
   - "기타": 그 외
5. 학생이 이해할 수 있는 언어로 구체적인 피드백
6. 문제 내용을 보고 어떤 수학 단원인지 스스로 판단해주세요. 이미지에 단원명이 없어도 문제 유형(사인 법칙, 조건부 확률, 이차방정식 등)을 보면 단원을 알 수 있습니다.

**응답 형식:**
```json
{{
  "homework_title": "숙제 제목 (이미지에서 확인 가능하면 기재, 없으면 단원명 사용)",
  "inferred_unit": "문제 내용으로 판단한 단원명 (예: 사인 법칙, 조건부 확률, 이차방정식)",
  "total_problems": 5,
  "correct_count": 3,
  "overall_feedback": "전반적인 한 줄 피드백",
  "image_quality": "good 또는 poor(흐림/기울어짐) 또는 unreadable(판독불가)",
  "problems": [
    {{
      "problem_number": "1a",
      "is_correct": true,
      "student_answer": "학생이 실제로 쓴 답",
      "correct_answer": "정답",
      "error_type": null,
      "feedback": "잘 풀었어요!"
    }},
    {{
      "problem_number": "1b",
      "is_correct": false,
      "student_answer": "학생이 실제로 쓴 답",
      "correct_answer": "정답",
      "error_type": "계산실수",
      "feedback": "공식은 맞게 썼는데 마지막 나눗셈에서 실수했어요. 3 ÷ 6 = 0.5예요."
    }}
  ]
}}
```

image_quality가 unreadable이면 problems는 빈 배열, overall_feedback에 사유 기재.
"""

# 하위 호환성 — grader.py 등에서 직접 import 하던 상수 유지
GRADING_USER = grading_user_prompt()

PATTERN_ANALYSIS_SYSTEM = """당신은 수학 과외 선생님의 학습 분석 도우미입니다.
학생의 오답 데이터를 분석하여 패턴과 인사이트를 도출합니다."""

def pattern_analysis_prompt(student_name: str, wrong_answers: list[dict]) -> str:
    rows_text = "\n".join(
        f"- [{r.get('날짜','')}] {r.get('숙제제목','')} 문제{r.get('문제번호','')} | "
        f"유형: {r.get('오답유형','')} | 피드백: {r.get('피드백','')}"
        for r in wrong_answers
    )
    return f"""학생 이름: {student_name}
누적 오답 데이터:
{rows_text}

위 데이터를 분석해서 다음 JSON 형식으로만 응답해주세요:

```json
{{
  "dominant_error_types": ["가장 많은 오답 유형 1", "유형 2"],
  "consecutive_same_error": true,
  "pattern_summary": "3줄 이내 패턴 요약",
  "next_lesson_focus": ["다음 수업 집중 포인트 1", "포인트 2"],
  "improvement_suggestions": ["개선 제안 1", "제안 2"]
}}
```"""


WEEKLY_REPORT_SYSTEM = """당신은 수학 과외 선생님의 주간 리포트 작성 도우미입니다.
선생님이 빠르게 읽을 수 있도록 핵심 정보를 간결하게 정리합니다."""

def weekly_report_prompt(week_start: str, students_data: dict[str, list[dict]]) -> str:
    lines = []
    for name, records in students_data.items():
        error_types = [r.get("오답유형", "") for r in records if r.get("오답유형")]
        lines.append(f"- {name}: 오답 {len(records)}건, 유형: {', '.join(set(error_types)) or '없음'}")
    summary = "\n".join(lines) if lines else "이번 주 제출 없음"

    return f"""이번 주({week_start}) 숙제 현황:
{summary}

위 데이터를 바탕으로 다음 JSON 형식으로만 응답해주세요:

```json
{{
  "week": "{week_start}",
  "student_summaries": [
    {{
      "name": "학생이름",
      "submission_count": 제출횟수,
      "wrong_count": 오답수,
      "main_error_type": "주요 오답 유형",
      "next_lesson_point": "다음 수업 포인트 한 줄"
    }}
  ],
  "overall_memo": "전체 한 줄 메모"
}}
```"""


MONTHLY_REPORT_SYSTEM = """당신은 수학 과외 선생님의 월간 리포트 초안 작성 도우미입니다.
학부모님이 읽기 쉽도록 bullet point 위주로 간결하게 작성합니다.
인사말은 생략하고, "데이터 분석" 같은 기술적 표현 대신 학습 상황을 자연스럽게 표현하세요."""

def monthly_report_prompt(student_name: str, month_label: str,
                           wrong_answers: list[dict], pattern: dict) -> str:
    total_wrong = len(wrong_answers)
    total_problems = len(wrong_answers) * 3  # 오답만 기록되므로 추정
    error_dist = {}
    for r in wrong_answers:
        t = r.get("오답유형", "기타")
        error_dist[t] = error_dist.get(t, 0) + 1

    dist_text = ", ".join(f"{k} {v}건" for k, v in error_dist.items()) or "없음"
    focus = ", ".join(pattern.get("next_lesson_focus", []))
    suggestions = "\n".join(f"- {s}" for s in pattern.get("improvement_suggestions", []))

    return f"""학생: {student_name}
기간: {month_label}
이번 달 오답: {total_wrong}건
오답 유형: {dist_text}
패턴: {pattern.get('pattern_summary', '')}
다음 달 집중 포인트: {focus}
개선 제안:
{suggestions}

위 내용을 바탕으로 학부모님께 드릴 월간 리포트 초안을 아래 JSON 형식으로 작성해주세요.
- 인사말 없이 바로 내용으로 시작
- 각 항목은 bullet point(•) 3~5개로 간결하게
- "데이터", "분석" 같은 표현 금지, 학습 상황을 자연스럽게
- 따뜻하고 긍정적인 어투

```json
{{
  "student_name": "{student_name}",
  "month": "{month_label}",
  "this_month_summary": ["• 이번 달 학습 현황 bullet 1", "• bullet 2", "• bullet 3"],
  "strengths": ["• 잘하는 점 1", "• 잘하는 점 2"],
  "growth_areas": ["• 더 연습하면 좋을 부분 1 (긍정적 표현)", "• 부분 2"],
  "next_month_plan": ["• 다음 달 계획 1", "• 계획 2", "• 계획 3"]
}}
```"""


HOMEWORK_SUGGESTION_SYSTEM = """당신은 수학 과외 선생님의 숙제 설계 도우미입니다.
학생의 오답 패턴을 보고 다음 숙제로 무엇을 내면 좋을지 구체적으로 추천합니다.
문제집 이름보다는 문제 유형과 난이도, 문항 수를 중심으로 추천하세요."""

def homework_suggestion_prompt(student_name: str, recent_wrong: list[dict], unit: str = "") -> str:
    rows = "\n".join(
        f"- {r.get('날짜','')} | {r.get('단원','')} {r.get('문제번호','')}번 | "
        f"{r.get('오답유형','')} | {r.get('AI해설','')[:60]}"
        for r in recent_wrong[-10:]
    )
    unit_hint = f"다음 수업 단원: {unit}" if unit else ""
    return f"""학생: {student_name}
{unit_hint}
최근 오답 내역:
{rows if rows else '오답 기록 없음'}

위 내용을 바탕으로 다음 숙제를 추천해주세요. JSON 형식으로만 응답하세요.

```json
{{
  "student_name": "{student_name}",
  "rationale": "추천 이유 한 줄 (오답 패턴 기반, 자연스럽게)",
  "assignments": [
    {{
      "type": "문제 유형 (예: 조건부 확률 기본)",
      "count": 5,
      "difficulty": "기본/응용/심화",
      "note": "어떤 점에 집중해서 풀어야 하는지"
    }}
  ],
  "total_estimated_time": "예상 풀이 시간 (예: 30~40분)"
}}
```"""
