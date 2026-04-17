"""
설정 파일 — .env 에서 값을 읽어옵니다.
.env.example 을 복사해서 .env 로 만들고 값을 채워주세요.
"""

import os
from dotenv import load_dotenv

load_dotenv(override=True)

# ─── Google API ───────────────────────────────────────────────
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "service_account.json")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "")

FORM_RESPONSE_SHEET = "설문지 응답 시트1"
WRONG_ANSWER_SHEET = "오답노트"

# ─── Claude API ───────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-opus-4-7"

# ─── Discord ──────────────────────────────────────────────────
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

# ─── Notion ───────────────────────────────────────────────────
NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "")

# ─── 앱 동작 설정 ─────────────────────────────────────────────
POLLING_INTERVAL_SECONDS = 60
DOWNLOAD_DIR = "downloads"
MIN_IMAGE_QUALITY_SCORE = 30

# SQLite 데이터베이스 경로
DB_PATH = "tutoring.db"

# ─── 구글폼 열 이름 (실제 폼 응답 시트에 맞게 수정) ───────────
FORM_COLUMNS = {
    "timestamp": "타임스탬프",
    "student_name": "학생",
    "homework_title": "단원명",
    "file_links": "숙제 업로드",
}

# 오답노트 시트 헤더 — 순서 변경 시 sheets_monitor.append_wrong_answers도 함께 수정
WRONG_ANSWER_COLUMNS = ["날짜", "학생", "단원", "문제번호", "정답여부", "학생답안", "정답", "오답유형", "AI해설", "숙제추천"]

# 파일 이름 양식: YYYYMMDD_학생이름_단원명_페이지번호.확장자
FILE_NAME_FORMAT = "{date}_{student}_{unit}_{page:02d}{ext}"
