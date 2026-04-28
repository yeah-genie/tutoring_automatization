"""
알림 전송 모듈 — Discord 웹훅 전용.
"""

import logging
from pathlib import Path

import requests

import config

logger = logging.getLogger(__name__)


class Notifiers:
    def discord(self, content: str, embeds: list[dict] | None = None):
        """Discord 웹훅으로 메시지 전송."""
        if not config.DISCORD_WEBHOOK_URL:
            logger.warning("DISCORD_WEBHOOK_URL이 .env에 설정되지 않았습니다.")
            return

        payload: dict = {"content": content}
        if embeds:
            payload["embeds"] = embeds

        try:
            r = requests.post(config.DISCORD_WEBHOOK_URL, json=payload, timeout=10)
            r.raise_for_status()
        except requests.RequestException as e:
            logger.error("Discord 전송 실패: %s", e)

    def discord_grading_complete(self, student_name: str, homework_title: str, result: dict):
        """채점 완료 알림."""
        total = result.get("total_problems", "?")
        correct = result.get("correct_count", "?")

        try:
            pct = int(correct) / int(total) * 100
            score_str = f"{correct}/{total} ({pct:.0f}%)"
            wrong_count = int(total) - int(correct)
            color = 0x57F287 if pct >= 80 else (0xFEE75C if pct >= 60 else 0xED4245)
        except (ValueError, ZeroDivisionError):
            score_str = f"{correct}/{total}"
            wrong_count = "?"
            color = 0x99AAB5

        embed = {
            "title": f"✅ 채점 완료 — {student_name}",
            "color": color,
            "fields": [
                {"name": "숙제", "value": homework_title, "inline": True},
                {"name": "점수", "value": score_str, "inline": True},
                {"name": "오답", "value": f"{wrong_count}건", "inline": True},
                {"name": "종합 피드백", "value": result.get("overall_feedback", "—"), "inline": False},
            ],
        }

        error_counts: dict[str, int] = {}
        for p in result.get("problems", []):
            if not p.get("is_correct") and p.get("error_type"):
                t = p["error_type"]
                error_counts[t] = error_counts.get(t, 0) + 1
        if error_counts:
            top = sorted(error_counts.items(), key=lambda x: -x[1])
            embed["fields"].append({
                "name": "오답 유형",
                "value": " / ".join(f"{k} {v}건" for k, v in top),
                "inline": False,
            })

        self.discord("", embeds=[embed])

    def discord_duplicate_detected(self, student_name: str, filename: str, reason: str):
        self.discord(
            f"⚠️ **중복 파일 감지** — {student_name}\n"
            f"파일명: `{filename}`\n이유: {reason}\n해당 파일은 채점에서 제외됩니다."
        )

    def discord_low_quality(self, student_name: str, filename: str, score: float):
        self.discord(
            f"📷 **이미지 품질 낮음** — {student_name}\n"
            f"파일: `{filename}` (품질 점수: {score}/100)\n"
            f"채점은 진행하지만 정확도가 낮을 수 있어요. 학생에게 재촬영 요청을 고려해보세요."
        )

    def discord_weekly_report(self, report: dict):
        """주간 리포트 Discord 전송."""
        if not report:
            self.discord("📊 주간 리포트 생성 실패")
            return

        fields = []
        for s in report.get("student_summaries", []):
            fields.append({
                "name": s.get("name", ""),
                "value": (
                    f"제출 {s.get('submission_count', 0)}회 | "
                    f"오답 {s.get('wrong_count', 0)}건 | "
                    f"주요유형: {s.get('main_error_type', '없음')}\n"
                    f"👉 {s.get('next_lesson_point', '')}"
                ),
                "inline": False,
            })

        self.discord("", embeds=[{
            "title": f"📊 주간 리포트 ({report.get('week', '')})",
            "description": report.get("overall_memo", ""),
            "color": 0x5865F2,
            "fields": fields[:25],
        }])

    def discord_monthly_draft_ready(self, student_name: str, notion_url: str):
        """월간 리포트 초안 완성 — Notion 링크 포함."""
        self.discord(
            f"📝 **월간 리포트 초안 완성** — {student_name}\n"
            f"노션에서 검토 후 학부모님께 직접 공유해주세요!\n"
            f"→ {notion_url}"
        )

    def discord_grading_with_explanation(self, student_name: str, unit: str, result: dict):
        """채점 완료 + 틀린 문제 해설 동시 전송."""
        total = result.get("total_problems", 0)
        correct = result.get("correct_count", 0)
        try:
            pct = int(correct) / int(total) * 100
            color = 0x57F287 if pct >= 80 else (0xFEE75C if pct >= 60 else 0xED4245)
            score_str = f"{correct}/{total} ({pct:.0f}%)"
        except (ValueError, ZeroDivisionError):
            pct, color, score_str = 0, 0x99AAB5, f"{correct}/{total}"

        wrong = [p for p in result.get("problems", []) if not p.get("is_correct")]
        error_counts: dict[str, int] = {}
        for p in wrong:
            t = p.get("error_type") or "기타"
            error_counts[t] = error_counts.get(t, 0) + 1

        display_unit = result.get("inferred_unit") or unit or "—"

        summary_embed = {
            "title": f"✅ 채점 완료 — {student_name}",
            "color": color,
            "fields": [
                {"name": "단원", "value": display_unit, "inline": True},
                {"name": "점수", "value": score_str, "inline": True},
                {"name": "오답 유형", "value": " / ".join(f"{k} {v}건" for k, v in error_counts.items()) or "없음", "inline": True},
                {"name": "종합 피드백", "value": result.get("overall_feedback", "—"), "inline": False},
            ],
        }

        explanation_lines = []
        for p in wrong:
            explanation_lines.append(
                f"**{p.get('problem_number','')}번** | "
                f"학생: {p.get('student_answer','?')} → 정답: {p.get('correct_answer','?')}\n"
                f"{p.get('feedback','')}"
            )
        embeds = [summary_embed]
        if explanation_lines:
            embeds.append({
                "title": "📝 틀린 문제 해설",
                "color": 0x5865F2,
                "description": "\n\n".join(explanation_lines)[:4000],
            })
        self.discord("", embeds=embeds)

    def discord_homework_suggestion(self, student_name: str, suggestion: dict):
        """숙제 추천 Discord 전송."""
        fields = []
        for a in suggestion.get("assignments", []):
            fields.append({
                "name": f"{a.get('type','')} ({a.get('difficulty','')})",
                "value": f"{a.get('count',0)}문제 — {a.get('note','')}",
                "inline": False,
            })
        fields.append({"name": "⏱️ 예상 시간", "value": suggestion.get("total_estimated_time", "—"), "inline": True})
        self.discord("", embeds=[{
            "title": f"📝 숙제 추천 — {student_name}",
            "description": suggestion.get("rationale", ""),
            "color": 0xFEE75C,
            "fields": fields,
        }])

    def discord_monthly_report(self, report: dict):
        """월간 리포트 Discord 전송 (bullet point 형식)."""
        def bullets(lst: list) -> str:
            return "\n".join(lst) if lst else "—"

        fields = [
            {"name": "📚 이번 달 학습 현황", "value": bullets(report.get("this_month_summary", [])), "inline": False},
            {"name": "✨ 잘하는 점", "value": bullets(report.get("strengths", [])), "inline": False},
            {"name": "📈 더 연습할 부분", "value": bullets(report.get("growth_areas", [])), "inline": False},
            {"name": "🗓️ 다음 달 계획", "value": bullets(report.get("next_month_plan", [])), "inline": False},
        ]
        self.discord("", embeds=[{
            "title": f"📋 {report.get('month','')} 리포트 — {report.get('student_name','')}",
            "color": 0x57F287,
            "fields": fields,
        }])

    def discord_send_pdf(self, pdf_path: Path, caption: str = ""):
        """Discord 웹훅에 PDF 파일 첨부 전송."""
        if not config.DISCORD_WEBHOOK_URL:
            return
        try:
            with open(pdf_path, "rb") as f:
                r = requests.post(
                    config.DISCORD_WEBHOOK_URL,
                    data={"content": caption},
                    files={"file": (pdf_path.name, f, "application/pdf")},
                    timeout=30,
                )
            r.raise_for_status()
            logger.info("Discord PDF 전송: %s", pdf_path.name)
        except requests.RequestException as e:
            logger.error("Discord PDF 전송 실패: %s", e)

    def discord_exam_ready(self, student_name: str, unit: str,
                           paper_path: Path, ms_path: Path, drive_url: str = ""):
        """시험지 + 해설지 생성 완료 알림 (파일 첨부)."""
        msg = f"📄 **Homework ready — {student_name}** | {unit}"
        if drive_url:
            msg += f"\n🔗 Drive: {drive_url}"
        self.discord_send_pdf(paper_path, caption=msg)
        self.discord_send_pdf(ms_path, caption="📋 Mark Scheme")

    def discord_anomaly_alerts(self, alerts: list):
        """이상탐지 알림 Discord 전송."""
        if not alerts:
            return

        fields = [
            {
                "name": f"{'🚨' if a.severity == 'critical' else '⚠️'} {a.student_name} — {a.alert_type}",
                "value": f"{a.description}\n👉 {a.recommendation}",
                "inline": False,
            }
            for a in alerts
        ]

        self.discord("", embeds=[{
            "title": "🔍 학습 이상 패턴 감지",
            "color": 0xED4245 if any(a.severity == "critical" for a in alerts) else 0xFEE75C,
            "fields": fields[:25],
        }])
