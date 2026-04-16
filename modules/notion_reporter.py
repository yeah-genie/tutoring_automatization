"""
Notion 월간 리포트 모듈.
- 학생별 데이터베이스 페이지 자동 생성
- 초안 내용을 블록으로 채워넣기
- 페이지 URL 반환
"""

import logging
from datetime import datetime

from notion_client import Client

import config

logger = logging.getLogger(__name__)


class NotionReporter:
    def __init__(self):
        self.notion = Client(auth=config.NOTION_TOKEN)
        self.database_id = config.NOTION_DATABASE_ID

    def create_monthly_draft(
        self,
        student_name: str,
        year: int,
        month: int,
        draft: dict,
        pattern: dict,
    ) -> str:
        """
        월간 리포트 초안을 Notion에 생성하고 URL 반환.
        draft: grader.generate_monthly_report_draft() 결과
        """
        month_label = f"{year}년 {month}월"
        title = f"[초안] {student_name} — {month_label} 리포트"

        # 데이터베이스에 새 페이지 생성
        page = self.notion.pages.create(
            parent={"database_id": self.database_id},
            properties={
                "Name": {"title": [{"text": {"content": title}}]},
                "학생": {"rich_text": [{"text": {"content": student_name}}]},
                "월": {"rich_text": [{"text": {"content": month_label}}]},
                "상태": {"select": {"name": "검토 필요"}},
                "생성일": {"date": {"start": datetime.now().strftime("%Y-%m-%d")}},
            },
            children=self._build_blocks(draft, pattern, month_label),
        )

        page_id = page["id"]
        url = f"https://notion.so/{page_id.replace('-', '')}"
        logger.info("Notion 페이지 생성: %s → %s", title, url)
        return url

    def _build_blocks(self, draft: dict, pattern: dict, month_label: str) -> list[dict]:
        blocks = []

        def h2(text: str) -> dict:
            return {"object": "block", "type": "heading_2",
                    "heading_2": {"rich_text": [{"type": "text", "text": {"content": text}}]}}

        def p(text: str) -> dict:
            return {"object": "block", "type": "paragraph",
                    "paragraph": {"rich_text": [{"type": "text", "text": {"content": text or "—"}}]}}

        def callout(text: str, emoji: str = "💡") -> dict:
            return {
                "object": "block",
                "type": "callout",
                "callout": {
                    "rich_text": [{"type": "text", "text": {"content": text}}],
                    "icon": {"type": "emoji", "emoji": emoji},
                },
            }

        def bullet(text: str) -> dict:
            return {"object": "block", "type": "bulleted_list_item",
                    "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": text}}]}}

        def divider() -> dict:
            return {"object": "block", "type": "divider", "divider": {}}

        # ─── 상단 안내 ────────────────────────────────────────
        blocks.append(callout(
            f"이 문서는 AI가 생성한 초안입니다. 검토 후 직접 수정하고 학부모님께 카톡으로 보내주세요.",
            "⚠️"
        ))
        blocks.append(divider())

        # ─── 인사말 ───────────────────────────────────────────
        blocks.append(h2("인사말"))
        blocks.append(p(draft.get("greeting", "")))
        blocks.append(divider())

        # ─── 수업 내용 요약 ───────────────────────────────────
        blocks.append(h2(f"{month_label} 수업 내용"))
        blocks.append(p(draft.get("curriculum_summary", "")))
        blocks.append(divider())

        # ─── 잘한 점 ──────────────────────────────────────────
        blocks.append(h2("잘하는 부분 ✨"))
        blocks.append(p(draft.get("strengths", "")))
        blocks.append(divider())

        # ─── 개선 필요 ────────────────────────────────────────
        blocks.append(h2("개선 포인트"))
        blocks.append(p(draft.get("improvement_areas", "")))
        blocks.append(divider())

        # ─── 데이터 분석 ──────────────────────────────────────
        blocks.append(h2("📊 학습 데이터 분석"))
        blocks.append(p(draft.get("data_insights", "")))

        # 오답 패턴
        if pattern.get("dominant_error_types"):
            blocks.append(p("주요 오답 유형:"))
            for t in pattern["dominant_error_types"]:
                blocks.append(bullet(t))

        if pattern.get("consecutive_same_error"):
            blocks.append(callout("3회 이상 연속으로 같은 유형의 실수가 있습니다. 다음 수업에서 집중 보완이 필요해요.", "🔁"))

        blocks.append(divider())

        # ─── 다음 달 계획 ─────────────────────────────────────
        blocks.append(h2("다음 달 계획 📅"))
        blocks.append(p(draft.get("next_month_plan", "")))
        if pattern.get("next_lesson_focus"):
            blocks.append(p("집중 학습 포인트:"))
            for item in pattern["next_lesson_focus"]:
                blocks.append(bullet(item))
        blocks.append(divider())

        # ─── 마무리 ───────────────────────────────────────────
        blocks.append(h2("마무리"))
        blocks.append(p(draft.get("closing", "")))

        return blocks

    def list_pending_drafts(self) -> list[dict]:
        """'검토 필요' 상태인 초안 목록 조회."""
        try:
            result = self.notion.databases.query(
                database_id=self.database_id,
                filter={"property": "상태", "select": {"equals": "검토 필요"}},
            )
            return [
                {
                    "id": p["id"],
                    "title": p["properties"]["Name"]["title"][0]["text"]["content"]
                    if p["properties"]["Name"]["title"] else "제목 없음",
                    "url": f"https://notion.so/{p['id'].replace('-', '')}",
                }
                for p in result.get("results", [])
            ]
        except Exception as e:
            logger.error("Notion 초안 목록 조회 실패: %s", e)
            return []
