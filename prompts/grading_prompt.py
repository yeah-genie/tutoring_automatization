"""
Claude API에 전달할 프롬프트 모음.
"""

GRADING_SYSTEM = """당신은 수학 과외 선생님의 숙제 채점 도우미입니다.
학생이 제출한 숙제 사진이나 PDF를 분석하여 정확하고 친절한 피드백을 제공합니다.
반드시 JSON 형식으로만 응답하고, JSON 외 다른 텍스트는 포함하지 마세요."""

GRADING_USER = """다음 숙제 이미지를 분석해서 아래 JSON 형식으로만 응답해주세요.

**분석 항목:**
- 각 문제의 정오 판정
- 오답인 경우 오답 유형 분류:
  * "개념부족": 개념 이해 부족으로 인한 오류
  * "계산실수": 계산 과정의 단순 실수
  * "풀이순서": 풀이 방법/순서 오류
  * "문제이해": 문제 해석 오류
  * "기타": 그 외
- 학생 답안과 정답
- 구체적인 피드백 (학생이 이해할 수 있는 언어로)

**응답 형식:**
```json
{
  "homework_title": "숙제 제목 (이미지에서 확인 가능하면 기재)",
  "total_problems": 문제수,
  "correct_count": 맞은문제수,
  "overall_feedback": "전반적인 한 줄 피드백",
  "problems": [
    {
      "problem_number": "1",
      "is_correct": true,
      "student_answer": "학생이 쓴 답",
      "correct_answer": "정답",
      "error_type": null,
      "feedback": "잘 풀었어요!"
    },
    {
      "problem_number": "2",
      "is_correct": false,
      "student_answer": "학생이 쓴 답",
      "correct_answer": "정답",
      "error_type": "계산실수",
      "feedback": "공식은 맞게 썼는데 마지막 나눗셈에서 실수했어요. 3 ÷ 6 = 2가 아니라 0.5예요."
    }
  ],
  "image_quality": "good"
}
```

image_quality는 "good", "poor" (흐림/기울어짐), "unreadable" (판독 불가) 중 하나.
판독 불가인 경우 problems는 빈 배열로, overall_feedback에 사유 기재.
"""

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
학부모님이 읽을 문서이므로 공식적이고 따뜻한 어투로 작성합니다."""

def monthly_report_prompt(student_name: str, month_label: str,
                           wrong_answers: list[dict], pattern: dict) -> str:
    total = len(wrong_answers)
    error_dist = {}
    for r in wrong_answers:
        t = r.get("오답유형", "기타")
        error_dist[t] = error_dist.get(t, 0) + 1

    dist_text = ", ".join(f"{k} {v}건" for k, v in error_dist.items()) or "없음"
    focus = ", ".join(pattern.get("next_lesson_focus", []))
    suggestions = "\n".join(f"- {s}" for s in pattern.get("improvement_suggestions", []))

    return f"""학생: {student_name}
기간: {month_label}
이번 달 총 오답: {total}건
오답 유형 분포: {dist_text}
패턴 요약: {pattern.get('pattern_summary', '')}
다음 달 집중 포인트: {focus}
개선 제안:
{suggestions}

위 데이터를 바탕으로 학부모님께 드릴 월간 리포트 초안을 다음 JSON 형식으로만 작성해주세요.
존댓말, 공식적이지만 따뜻한 어투로 작성하세요.

```json
{{
  "student_name": "{student_name}",
  "month": "{month_label}",
  "greeting": "학부모님께 드리는 인사말 (2~3문장)",
  "curriculum_summary": "이번 달 수업 내용 요약 (3~4문장)",
  "strengths": "잘하는 부분 (2~3문장)",
  "improvement_areas": "개선 필요한 부분 (2~3문장, 부정적이지 않게)",
  "data_insights": "오답 데이터 기반 분석 (3~4문장)",
  "next_month_plan": "다음 달 계획 (3~4문장)",
  "closing": "마무리 인사 (1~2문장)"
}}
```"""
