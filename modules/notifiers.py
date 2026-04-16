"""
알림 전송 모듈.
- Discord 웹훅: 채점 완료 알림, 주간 리포트
- KakaoTalk 나에게 보내기: 중요 알림
"""

import logging

import requests

import config

logger = logging.getLogger(__name__)

KAKAO_SEND_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"


class Notifiers:
    # ─── Discord ──────────────────────────────────────────────

    def discord(self, content: str, embeds: list[dict] | None = None):
        """Discord 웹훅으로 메시지 전송."""
        if not config.DISCORD_WEBHOOK_URL or "여기에" in config.DISCORD_WEBHOOK_URL:
            logger.warning("Discord 웹훅 URL이 설정되지 않았습니다.")
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
        """채점 완료 Discord 알림."""
        total = result.get("total_problems", "?")
        correct = result.get("correct_count", "?")
        score_pct = f"{int(correct)/int(total)*100:.0f}%" if str(total).isdigit() and str(correct).isdigit() and int(total) > 0 else "?"
        wrong_count = int(total) - int(correct) if str(total).isdigit() and str(correct).isdigit() else "?"

        color = 0x57F287 if score_pct != "?" and float(score_pct.replace("%","")) >= 80 else 0xFEE75C
        if score_pct != "?" and float(score_pct.replace("%","")) < 60:
            color = 0xED4245

        embed = {
            "title": f"✅ 채점 완료 — {student_name}",
            "color": color,
            "fields": [
                {"name": "숙제", "value": homework_title, "inline": True},
                {"name": "점수", "value": f"{correct}/{total} ({score_pct})", "inline": True},
                {"name": "오답", "value": f"{wrong_count}건", "inline": True},
                {"name": "종합 피드백", "value": result.get("overall_feedback", "—"), "inline": False},
            ],
        }

        # 주요 오답 유형 집계
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
        """중복 파일 감지 알림."""
        self.discord(
            f"⚠️ **중복 파일 감지** — {student_name}\n"
            f"파일명: `{filename}`\n이유: {reason}\n해당 파일은 채점에서 제외됩니다."
        )

    def discord_low_quality(self, student_name: str, filename: str, score: float):
        """이미지 품질 낮음 알림."""
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

        week = report.get("week", "")
        overall = report.get("overall_memo", "")
        summaries = report.get("student_summaries", [])

        fields = []
        for s in summaries:
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

        embed = {
            "title": f"📊 주간 리포트 ({week})",
            "description": overall,
            "color": 0x5865F2,
            "fields": fields[:25],  # Discord embed 필드 최대 25개
        }
        self.discord("", embeds=[embed])

    def discord_monthly_draft_ready(self, student_name: str, notion_url: str):
        """월간 리포트 초안 완성 알림 (Notion 링크 포함)."""
        self.discord(
            f"📝 **월간 리포트 초안 완성** — {student_name}\n"
            f"노션에서 검토 후 학부모님께 카톡으로 보내주세요!\n"
            f"→ {notion_url}"
        )

    # ─── KakaoTalk ────────────────────────────────────────────

    def kakao(self, text: str):
        """카카오톡 나에게 보내기."""
        if not config.KAKAO_ACCESS_TOKEN or "여기에" in config.KAKAO_ACCESS_TOKEN:
            logger.warning("카카오 액세스 토큰이 설정되지 않았습니다.")
            return

        template = {
            "object_type": "text",
            "text": text,
            "link": {"web_url": "", "mobile_web_url": ""},
        }
        try:
            r = requests.post(
                KAKAO_SEND_URL,
                headers={"Authorization": f"Bearer {config.KAKAO_ACCESS_TOKEN}"},
                data={"template_object": str(template).replace("'", '"')},
                timeout=10,
            )
            r.raise_for_status()
            logger.info("카카오 전송 완료")
        except requests.RequestException as e:
            logger.error("카카오 전송 실패: %s", e)
