"""
Google Sheets 모니터링 모듈.
- 폼 응답 시트에서 새 행 감지
- Google Drive에서 파일 다운로드
- 채점 결과를 오답노트 시트에 저장
"""

import io
import json
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

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]


class SheetsMonitor:
    def __init__(self):
        creds = Credentials.from_service_account_file(
            config.GOOGLE_SERVICE_ACCOUNT_JSON, scopes=SCOPES
        )
        self.gc = gspread.authorize(creds)
        self.drive = build("drive", "v3", credentials=creds)
        self.spreadsheet = self.gc.open_by_key(config.SPREADSHEET_ID)
        self._processed: set[int] = self._load_processed()
        Path(config.DOWNLOAD_DIR).mkdir(exist_ok=True)

    def _load_processed(self) -> set[int]:
        p = Path(config.PROCESSED_ROWS_FILE)
        if p.exists():
            with open(p, "r") as f:
                return set(json.load(f))
        return set()

    def _save_processed(self):
        with open(config.PROCESSED_ROWS_FILE, "w") as f:
            json.dump(list(self._processed), f)

    def get_new_submissions(self) -> Iterator[dict]:
        """처리하지 않은 새 폼 응답을 하나씩 yield."""
        sheet = self.spreadsheet.worksheet(config.FORM_RESPONSE_SHEET)
        records = sheet.get_all_records()

        for idx, row in enumerate(records):
            row_number = idx + 2  # 1-indexed + 헤더 행
            if row_number in self._processed:
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
                "file_links": self._parse_file_links(
                    row.get(config.FORM_COLUMNS["file_links"], "")
                ),
                "raw_row": row,
            }

    def mark_processed(self, row_number: int):
        self._processed.add(row_number)
        self._save_processed()

    def download_drive_file(self, file_id: str, filename: str) -> Path | None:
        """Drive 파일 ID로 다운로드 후 로컬 경로 반환."""
        dest = Path(config.DOWNLOAD_DIR) / filename
        if dest.exists():
            return dest
        try:
            request = self.drive.files().get_media(fileId=file_id)
            buf = io.BytesIO()
            downloader = MediaIoBaseDownload(buf, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            dest.write_bytes(buf.getvalue())
            logger.info("다운로드 완료: %s", filename)
            return dest
        except Exception as e:
            logger.error("Drive 다운로드 실패 (%s): %s", file_id, e)
            return None

    def append_wrong_answers(self, student_name: str, homework_title: str, results: list[dict]):
        """
        채점 결과를 오답노트 시트에 추가.
        results: grader.py가 반환하는 problem 결과 목록
        """
        sheet = self.spreadsheet.worksheet(config.WRONG_ANSWER_SHEET)
        today = datetime.now().strftime("%Y-%m-%d")

        rows_to_append = []
        for r in results:
            if r.get("is_correct"):
                continue
            rows_to_append.append([
                today,
                student_name,
                homework_title,
                r.get("problem_number", ""),
                r.get("error_type", ""),        # 개념부족 / 계산실수 / 풀이순서 / 기타
                r.get("student_answer", ""),
                r.get("correct_answer", ""),
                r.get("feedback", ""),
            ])

        if rows_to_append:
            sheet.append_rows(rows_to_append, value_input_option="USER_ENTERED")
            logger.info("%s - 오답 %d건 저장", student_name, len(rows_to_append))

    def get_wrong_answer_history(self, student_name: str) -> list[dict]:
        """학생의 누적 오답 이력 조회 (패턴 분석용)."""
        sheet = self.spreadsheet.worksheet(config.WRONG_ANSWER_SHEET)
        records = sheet.get_all_records()
        return [r for r in records if r.get("학생 이름", "") == student_name or
                r.get("이름", "") == student_name]

    def get_all_students_weekly(self, start_date: str) -> dict[str, list[dict]]:
        """주간 리포트용: 날짜 이후 오답 데이터를 학생별로 그룹화."""
        sheet = self.spreadsheet.worksheet(config.WRONG_ANSWER_SHEET)
        records = sheet.get_all_records()
        result: dict[str, list] = {}
        for r in records:
            date_str = str(r.get("날짜", r.get("타임스탬프", "")))[:10]
            if date_str >= start_date:
                name = r.get("학생 이름", r.get("이름", "Unknown"))
                result.setdefault(name, []).append(r)
        return result

    def get_monthly_data(self, student_name: str, year: int, month: int) -> list[dict]:
        """월간 리포트용: 특정 학생의 월 전체 데이터."""
        prefix = f"{year}-{month:02d}"
        history = self.get_wrong_answer_history(student_name)
        return [r for r in history if str(r.get("날짜", "")).startswith(prefix)]

    @staticmethod
    def _parse_file_links(raw: str) -> list[str]:
        """폼 응답의 Drive 링크 문자열을 파일 ID 목록으로 변환."""
        if not raw:
            return []
        # 쉼표나 줄바꿈으로 구분된 링크들 처리
        links = re.split(r"[,\n]+", raw.strip())
        file_ids = []
        for link in links:
            link = link.strip()
            # https://drive.google.com/file/d/{id}/view 형식
            m = re.search(r"/file/d/([^/\?]+)", link)
            if m:
                file_ids.append(m.group(1))
                continue
            # https://drive.google.com/open?id={id} 형식
            m = re.search(r"[?&]id=([^&]+)", link)
            if m:
                file_ids.append(m.group(1))
        return file_ids
