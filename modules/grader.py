"""
Claude Vision 채점 모듈.
이미지를 Claude API에 전송하고 채점 결과를 파싱한다.
"""

import json
import logging
import re
from pathlib import Path

import anthropic

import config
from modules.anonymizer import Anonymizer
from modules.image_processor import to_base64
from prompts.grading_prompt import (
    GRADING_SYSTEM,
    grading_user_prompt,
    PATTERN_ANALYSIS_SYSTEM,
    WEEKLY_REPORT_SYSTEM,
    MONTHLY_REPORT_SYSTEM,
    pattern_analysis_prompt,
    weekly_report_prompt,
    monthly_report_prompt,
)

logger = logging.getLogger(__name__)


class Grader:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self._anon = Anonymizer()

    def grade_submission(self, image_paths: list[Path], unit: str = "") -> dict:
        """
        한 학생의 제출 파일(이미지 목록)을 채점.
        여러 이미지를 하나의 요청으로 묶어서 비용 절감.
        Returns: 채점 결과 dict
        """
        if not image_paths:
            return {"error": "이미지 없음", "problems": []}

        content = []
        for path in image_paths:
            b64, media_type = to_base64(path)
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": b64,
                },
            })
        content.append({"type": "text", "text": grading_user_prompt(unit)})

        try:
            response = self.client.messages.create(
                model=config.CLAUDE_MODEL,
                max_tokens=16384,
                system=GRADING_SYSTEM,
                messages=[{"role": "user", "content": content}],
            )
            raw = response.content[0].text
            return self._parse_json_response(raw)
        except Exception as e:
            logger.error("채점 API 호출 실패: %s", e)
            return {"error": str(e), "problems": []}

    def analyze_patterns(self, student_name: str, wrong_answers: list[dict]) -> dict:
        """누적 오답 데이터로 패턴 분석."""
        if not wrong_answers:
            return {
                "dominant_error_types": [],
                "consecutive_same_error": False,
                "pattern_summary": "아직 오답 데이터가 없습니다.",
                "next_lesson_focus": [],
                "improvement_suggestions": [],
            }

        prompt = pattern_analysis_prompt(self._anon.mask(student_name), wrong_answers)
        try:
            response = self.client.messages.create(
                model=config.CLAUDE_MODEL,
                max_tokens=1024,
                system=PATTERN_ANALYSIS_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            return self._parse_json_response(response.content[0].text)
        except Exception as e:
            logger.error("패턴 분석 실패: %s", e)
            return {}

    def generate_weekly_report(self, week_start: str, students_data: dict[str, list[dict]]) -> dict:
        """주간 리포트 생성 (Discord 전송용)."""
        prompt = weekly_report_prompt(week_start, self._anon.mask_dict(students_data))
        try:
            response = self.client.messages.create(
                model=config.CLAUDE_MODEL,
                max_tokens=2048,
                system=WEEKLY_REPORT_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            return self._parse_json_response(response.content[0].text)
        except Exception as e:
            logger.error("주간 리포트 생성 실패: %s", e)
            return {}

    def generate_monthly_report_draft(
        self,
        student_name: str,
        month_label: str,
        wrong_answers: list[dict],
        pattern: dict,
    ) -> dict:
        """월간 리포트 초안 생성 (Notion 저장용)."""
        prompt = monthly_report_prompt(self._anon.mask(student_name), month_label, wrong_answers, pattern)
        try:
            response = self.client.messages.create(
                model=config.CLAUDE_MODEL,
                max_tokens=3000,
                system=MONTHLY_REPORT_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            return self._parse_json_response(response.content[0].text)
        except Exception as e:
            logger.error("월간 리포트 초안 생성 실패: %s", e)
            return {}

    @staticmethod
    def _parse_json_response(raw: str) -> dict:
        """Claude 응답에서 JSON 블록 추출 및 파싱."""
        # ```json ... ``` 블록 추출 시도 (greedy로 중첩 JSON 보존)
        match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.DOTALL)
        if match:
            raw = match.group(1)
        else:
            # 첫 번째 { 부터 마지막 } 까지 추출
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end != -1:
                raw = raw[start:end + 1]
            else:
                raw = raw.strip()

        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error("JSON 파싱 실패: %s\n원문: %s", e, raw[:200])
            return {"parse_error": str(e), "raw": raw[:500]}
