"""
Google Sheets 모니터링 모듈.
- 폼 응답 시트에서 새 행 감지
- Google Drive에서 파일 다운로드 (원본 파일명·확장자 보존)
- 채점 결과를 오답노트 시트에 저장
"""

import io
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Iterator

import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

import config
from modules.db import Database

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

MIME_TO_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}


class SheetsMonitor:
    def __init__(self, db: Database):
        self.db = db
        creds = Credentials.from_service_account_file(
            config.GOOGLE_SERVICE_ACCOUNT_JSON, scopes=SCOPES
        )
        self.gc = gspread.authorize(creds)
        self.drive = build("drive", "v3", credentials=creds)
        self.spreadsheet = self.gc.open_by_key(config.SPREADSHEET_ID)
        Path(config.DOWNLOAD_DIR).mkdir(exist_ok=True)

    def get_new_submissions(self) -> Iterator[dict]:
        """처리하지 않은 새 폼 응답을 하나씩 yield."""
        sheet = self.spreadsheet.worksheet(config.FORM_RESPONSE_SHEET)
        records = sheet.get_all_records()

        for idx, row in enumerate(records):
            row_number = idx + 2
            if self.db.is_processed(row_number):
                continue

            student_name = row.get(config.FORM_COLUMNS["student_name"], "").strip()
            if not student_name:
                continue

            yield {
                "row_number": row_number,
                "timestamp": row.get(config.FORM_COLUMNS["timestamp"], ""),
                "student_name": student_name,
                "subject": row.get(config.FORM_COLUMNS.get("subject", ""), ""),
                "homework_title": row.get(config.FORM_COLUMNS["homework_title"], ""),
                "file_ids": self._parse_file_ids(
                    row.get(config.FORM_COLUMNS["file_links"], "")
                ),
            }

    def download_drive_file(self, file_id: str, student_name: str) -> Path | None:
        """
        Drive 파일 ID로 다운로드.
        파일 메타데이터를 먼저 조회해서 원본 이름과 확장자를 보존.
        """
        try:
            meta = self.drive.files().get(
                fileId=file_id, fields="name,mimeType"
            ).execute()
            original_name = meta.get("name", file_id)
            mime = meta.get("mimeType", "")

            # 원본 이름에 확장자가 없으면 mimeType 기반으로 추가
            stem = Path(original_name).stem
            suffix = Path(original_name).suffix or MIME_TO_EXT.get(mime, "")
            safe_student = re.sub(r"[^\w가-힣]", "_", student_name)
            filename = f"{safe_student}_{stem}{suffix}"

            dest = Path(config.DOWNLOAD_DIR) / filename
            if dest.exists():
                return dest

            request = self.drive.files().get_media(fileId=file_id)
            buf = io.BytesIO()
            downloader = MediaIoBaseDownload(buf, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            dest.write_bytes(buf.getvalue())
            logger.info("다운로드: %s", filename)
            return dest

        except Exception as e:
            logger.error("Drive 다운로드 실패 (%s): %s", file_id, e)
            return None

    def append_wrong_answers(self, student_name: str, homework_title: str, results: list[dict]):
        """채점 결과를 오답노트 시트에 추가."""
        sheet = self.spreadsheet.worksheet(config.WRONG_ANSWER_SHEET)
        today = datetime.now().strftime("%Y-%m-%d")

        rows_to_append = []
        for r in results:
            if r.get("is_correct"):
                continue
            # config.WRONG_ANSWER_COLUMNS 순서와 일치
            rows_to_append.append([
                today,
                student_name,
                homework_title,
                r.get("problem_number", ""),
                r.get("error_type", ""),
                r.get("student_answer", ""),
                r.get("correct_answer", ""),
                r.get("feedback", ""),
            ])

        if rows_to_append:
            sheet.append_rows(rows_to_append, value_input_option="USER_ENTERED")
            logger.info("%s — 오답 %d건 저장", student_name, len(rows_to_append))

    def get_wrong_answer_history(self, student_name: str) -> list[dict]:
        """학생 오답 이력. 컬럼명은 config.WRONG_ANSWER_COLUMNS 기준."""
        sheet = self.spreadsheet.worksheet(config.WRONG_ANSWER_SHEET)
        records = sheet.get_all_records()
        col = config.WRONG_ANSWER_COLUMNS[1]  # "학생 이름"
        return [r for r in records if r.get(col, "") == student_name]

    def get_all_students_weekly(self, start_date: str) -> dict[str, list[dict]]:
        sheet = self.spreadsheet.worksheet(config.WRONG_ANSWER_SHEET)
        records = sheet.get_all_records()
        date_col = config.WRONG_ANSWER_COLUMNS[0]
        name_col = config.WRONG_ANSWER_COLUMNS[1]
        result: dict[str, list] = {}
        for r in records:
            if str(r.get(date_col, ""))[:10] >= start_date:
                name = r.get(name_col, "Unknown")
                result.setdefault(name, []).append(r)
        return result

    def get_monthly_data(self, student_name: str, year: int, month: int) -> list[dict]:
        prefix = f"{year}-{month:02d}"
        date_col = config.WRONG_ANSWER_COLUMNS[0]
        return [
            r for r in self.get_wrong_answer_history(student_name)
            if str(r.get(date_col, "")).startswith(prefix)
        ]

    @staticmethod
    def _parse_file_ids(raw: str) -> list[str]:
        """폼 응답의 Drive 링크 문자열 → 파일 ID 목록."""
        if not raw:
            return []
        ids = []
        for link in re.split(r"[,\n]+", raw.strip()):
            link = link.strip()
            m = re.search(r"/file/d/([^/?\s]+)", link)
            if m:
                ids.append(m.group(1))
                continue
            m = re.search(r"[?&]id=([^&\s]+)", link)
            if m:
                ids.append(m.group(1))
        return ids
