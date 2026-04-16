"""
설정 파일 - API 키와 설정값을 여기에 입력하세요.
SETUP.md를 먼저 읽어주세요.
"""

# ─── Google API ───────────────────────────────────────────────
# 서비스 계정 JSON 키 파일 경로 (SETUP.md 참고)
GOOGLE_SERVICE_ACCOUNT_JSON = "service_account.json"

# 구글폼 응답이 저장되는 스프레드시트 ID
# URL: https://docs.google.com/spreadsheets/d/[이 부분]/edit
SPREADSHEET_ID = "1wbewy55HFxzKoRRtQdd5G5g9YG_6D19wKtcilPf66Z8"

# 스프레드시트 시트 이름
FORM_RESPONSE_SHEET = "설문지 응답 시트1"   # 폼 응답이 쌓이는 시트
WRONG_ANSWER_SHEET = "오답노트"              # 오답노트 시트

# ─── Claude API ───────────────────────────────────────────────
ANTHROPIC_API_KEY = "여기에_Claude_API_키_입력"
CLAUDE_MODEL = "claude-opus-4-7"             # Vision 지원 모델

# ─── Discord ──────────────────────────────────────────────────
# Discord 채널 웹훅 URL (SETUP.md 참고)
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/여기에_입력"

# ─── KakaoTalk (나에게 보내기) ────────────────────────────────
KAKAO_ACCESS_TOKEN = "여기에_카카오_액세스_토큰_입력"

# ─── Notion ───────────────────────────────────────────────────
NOTION_TOKEN = "여기에_Notion_인테그레이션_토큰_입력"
# 리포트를 생성할 Notion 데이터베이스 ID
# URL: https://notion.so/[이 부분]?v=...
NOTION_DATABASE_ID = "여기에_Notion_데이터베이스_ID_입력"

# ─── 앱 동작 설정 ─────────────────────────────────────────────
# Sheets 폴링 간격 (초)
POLLING_INTERVAL_SECONDS = 60

# 처리한 행 추적 파일
PROCESSED_ROWS_FILE = ".processed_rows.json"

# 중복 해시 저장 파일
DUPLICATE_HASHES_FILE = ".file_hashes.json"

# 다운로드 임시 폴더
DOWNLOAD_DIR = "downloads"

# 이미지 품질이 너무 낮을 때 재촬영 요청 기준 (0~100)
MIN_IMAGE_QUALITY_SCORE = 30

# ─── 학생 정보 ────────────────────────────────────────────────
# 구글폼 응답의 열 이름 (실제 폼에 맞게 수정하세요)
FORM_COLUMNS = {
    "timestamp": "타임스탬프",
    "student_name": "이름",
    "subject": "과목",
    "homework_title": "숙제 제목",
    "file_links": "파일 업로드",  # Drive 파일 링크
}
