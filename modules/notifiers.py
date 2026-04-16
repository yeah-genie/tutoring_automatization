"""
알림 전송 모듈 — Discord 웹훅 전용.
"""

import logging

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
