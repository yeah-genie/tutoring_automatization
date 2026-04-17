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
    "https://www.googleapis.com/auth/drive",
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

    def download_drive_file(
        self, file_id: str, student_name: str,
        unit: str = "", page: int = 1,
    ) -> Path | None:
        """
        Drive 파일 → 로컬 다운로드.
        파일명 형식: YYYYMMDD_학생이름_단원명_페이지.확장자
        """
        try:
            meta = self.drive.files().get(
                fileId=file_id, fields="name,mimeType"
            ).execute()
            mime = meta.get("mimeType", "")
            suffix = Path(meta.get("name", "")).suffix or MIME_TO_EXT.get(mime, "")

            date_str = datetime.now().strftime("%Y%m%d")
            safe_student = re.sub(r"[^\w가-힣]", "_", student_name)
            safe_unit = re.sub(r"[^\w가-힣]", "_", unit) if unit else "숙제"
            filename = f"{date_str}_{safe_student}_{safe_unit}_{page:02d}{suffix}"

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

    def upload_pdf_to_student_folder(
        self, pdf_path: Path, student_name: str, folder_map: dict[str, str]
    ) -> str | None:
        """
        PDF를 학생 Drive 폴더에 업로드.
        folder_map: {"학생이름": "folder_id", ...}
        Returns: uploaded file URL or None.
        """
        folder_id = folder_map.get(student_name)
        if not folder_id:
            logger.warning("학생 폴더 없음: %s", student_name)
            return None
        try:
            from googleapiclient.http import MediaFileUpload
            file_meta = {"name": pdf_path.name, "parents": [folder_id]}
            media = MediaFileUpload(str(pdf_path), mimetype="application/pdf")
            uploaded = self.drive.files().create(
                body=file_meta, media_body=media, fields="id,webViewLink"
            ).execute()
            url = uploaded.get("webViewLink", "")
            logger.info("Drive 업로드 완료: %s → %s", pdf_path.name, url)
            return url
        except Exception as e:
            logger.error("Drive 업로드 실패: %s", e)
            return None

    def append_wrong_answers(self, student_name: str, unit: str, results: list[dict]):
        """채점 결과를 오답노트 시트에 추가 (전 문제, 오답만 숙제추천 ✅).
        컬럼 순서: 날짜 / 학생 / 단원 / 문제번호 / 정답여부 / 학생답안 / 정답 / 오답유형 / AI해설 / 숙제추천
        """
        sheet = self.spreadsheet.worksheet(config.WRONG_ANSWER_SHEET)
        today = datetime.now().strftime("%Y-%m-%d")

        rows_to_append = []
        for r in results:
            is_correct = r.get("is_correct", False)
            rows_to_append.append([
                today,
                student_name,
                unit,
                r.get("problem_number", ""),
                "O" if is_correct else "X",
                r.get("student_answer", ""),
                r.get("correct_answer", ""),
                r.get("error_type", "") if not is_correct else "",
                r.get("feedback", ""),
                "✅" if not is_correct else "",   # 오답만 숙제추천 표시
            ])

        if rows_to_append:
            sheet.append_rows(rows_to_append, value_input_option="USER_ENTERED")
            wrong_count = sum(1 for r in rows_to_append if r[4] == "X")
            logger.info("%s — 전체 %d문제, 오답 %d건 저장", student_name, len(rows_to_append), wrong_count)

    def get_wrong_answer_history(self, student_name: str, wrong_only: bool = False) -> list[dict]:
        """학생 전체 이력. wrong_only=True면 오답(X)만 반환."""
        sheet = self.spreadsheet.worksheet(config.WRONG_ANSWER_SHEET)
        records = sheet.get_all_records()
        rows = [r for r in records if r.get("학생", "") == student_name]
        if wrong_only:
            rows = [r for r in rows if r.get("정답여부", "") == "X"]
        return rows

    def get_review_candidates(self, student_name: str, limit: int = 3) -> list[dict]:
        """복습 문제 후보: 최근 틀린 문제 중 숙제추천 ✅ 된 것 최대 limit개."""
        wrong = self.get_wrong_answer_history(student_name, wrong_only=True)
        candidates = [r for r in wrong if r.get("숙제추천", "") == "✅"]
        return candidates[-limit:]  # 가장 최근 것

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
