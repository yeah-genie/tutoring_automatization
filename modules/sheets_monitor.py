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
        """Drive 파일 → 로컬 다운로드.
        파일명 형식: YYYYMMDD_HHMMSS_학생이름_단원명_페이지.확장자
        """
        try:
            meta = self.drive.files().get(
                fileId=file_id, fields="name,mimeType"
            ).execute()
            mime = meta.get("mimeType", "")
            suffix = Path(meta.get("name", "")).suffix or MIME_TO_EXT.get(mime, "")

            now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_student = re.sub(r"\s+", "", student_name)
            safe_unit = re.sub(r"\s+", "", unit) if unit else "숙제"
            filename = f"{now_str}_{safe_student}_{safe_unit}_{page:02d}{suffix}"

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
        """PDF를 학생 Drive 폴더에 업로드. Returns: 파일 URL or None."""
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

    def list_drive_folder_contents(self, folder_id: str) -> dict[str, list[dict]]:
        """Drive 폴더를 재귀 탐색하여 단원별 파일 목록 반환.

        Returns:
            {단원명: [{"id": ..., "name": ..., "mimeType": ...}]}
            최상위 직접 파일은 "기타" 키로 묶음.
        """
        groups: dict[str, list] = {}

        def _scan(fid: str, unit_name: str):
            try:
                page_token = None
                while True:
                    kwargs = dict(
                        q=f"'{fid}' in parents and trashed=false",
                        fields="nextPageToken, files(id, name, mimeType)",
                        pageSize=100,
                    )
                    if page_token:
                        kwargs["pageToken"] = page_token
                    resp = self.drive.files().list(**kwargs).execute()
                    for item in resp.get("files", []):
                        mime = item["mimeType"]
                        if mime == "application/vnd.google-apps.folder":
                            _scan(item["id"], item["name"])
                        elif mime.startswith("image/") or mime == "application/pdf":
                            groups.setdefault(unit_name, []).append({
                                "id": item["id"],
                                "name": item["name"],
                                "mimeType": mime,
                            })
                    page_token = resp.get("nextPageToken")
                    if not page_token:
                        break
            except Exception as e:
                logger.error("Drive 스캔 실패 (%s): %s", fid, e)

        _scan(folder_id, "기타")
        return groups

    @staticmethod
    def _make_submission_id(student_name: str, unit: str) -> str:
        """제출ID 생성: YYYYMMDD_HHMMSS_학생이름_단원명 (초 단위 포함으로 충돌 방지)"""
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_student = re.sub(r"\s+", "", student_name)
        safe_unit = re.sub(r"\s+", "", unit) if unit else "숙제"
        return f"{now}_{safe_student}_{safe_unit}"

    def append_wrong_answers(self, student_name: str, unit: str, results: list[dict]):
        """채점 결과 중 오답만 오답노트 시트에 추가.
        컬럼 순서: 제출ID / 문제번호 / 학생답안 / 정답 / 오답유형 / AI해설 / 복습완료
        """
        sheet = self.spreadsheet.worksheet(config.WRONG_ANSWER_SHEET)
        submission_id = self._make_submission_id(student_name, unit)

        rows_to_append = []
        for r in results:
            if not r.get("is_correct", False):
                rows_to_append.append([
                    submission_id,
                    r.get("problem_number", ""),
                    r.get("student_answer", ""),
                    r.get("correct_answer", ""),
                    r.get("error_type", ""),
                    r.get("feedback", ""),
                    "",  # 복습완료 — 처음엔 빈칸
                ])

        if rows_to_append:
            sheet.append_rows(rows_to_append, value_input_option="USER_ENTERED")
            logger.info("%s — 오답 %d건 오답노트 저장 (제출ID: %s)", student_name, len(rows_to_append), submission_id)
        else:
            logger.info("%s — 오답 없음, 오답노트 저장 생략", student_name)

    def write_submission_record(
        self, student_name: str, unit: str,
        total_problems: int, correct_count: int,
    ):
        """채점 완료 후 제출기록 시트에 요약 1행 추가.
        컬럼 순서: 제출ID / 날짜 / 학생 / 단원 / 총문제수 / 정답수 / 오답수
        """
        try:
            sheet = self.spreadsheet.worksheet(config.SUBMISSION_RECORD_SHEET)
            today = datetime.now().strftime("%Y-%m-%d")
            submission_id = self._make_submission_id(student_name, unit)
            wrong_count = total_problems - correct_count
            sheet.append_rows(
                [[submission_id, today, student_name, unit, total_problems, correct_count, wrong_count]],
                value_input_option="USER_ENTERED",
            )
            logger.info("제출기록 저장: %s", submission_id)
        except Exception as e:
            logger.error("제출기록 저장 실패: %s", e)

    def clear_sheet(self, sheet_name: str):
        """지정 시트의 헤더(1행)를 제외한 모든 데이터 삭제."""
        try:
            sheet = self.spreadsheet.worksheet(sheet_name)
            all_values = sheet.get_all_values()
            if len(all_values) > 1:
                sheet.delete_rows(2, len(all_values))
                logger.info("%s 시트 데이터 전체 삭제 완료 (%d행)", sheet_name, len(all_values) - 1)
            else:
                logger.info("%s 시트 — 삭제할 데이터 없음", sheet_name)
        except Exception as e:
            logger.error("시트 삭제 실패 (%s): %s", sheet_name, e)

    def get_wrong_answer_history(self, student_name: str) -> list[dict]:
        """학생 오답 이력 반환.
        제출ID 형식: YYYYMMDD_HHMMSS_학생이름_단원명 → 3번째 토큰이 학생이름으로 정확 매칭.
        """
        sheet = self.spreadsheet.worksheet(config.WRONG_ANSWER_SHEET)
        records = sheet.get_all_records()
        safe_student = re.sub(r"\s+", "", student_name)
        result = []
        for r in records:
            sid = r.get("제출ID", "")
            parts = sid.split("_", 3)  # ["YYYYMMDD", "HHMMSS", "학생이름", "단원"]
            if len(parts) >= 3 and parts[2] == safe_student:
                result.append(r)
        return result

    def get_review_candidates(self, student_name: str, limit: int = 3) -> list[dict]:
        """복습 미완료 오답 후보 최대 limit개."""
        wrong = self.get_wrong_answer_history(student_name)
        candidates = [r for r in wrong if not r.get("복습완료", "")]
        return candidates[-limit:]

    def get_all_students_weekly(self, start_date: str) -> dict[str, list[dict]]:
        """시작일 이후 제출기록 시트에서 학생별 데이터 집계."""
        try:
            sheet = self.spreadsheet.worksheet(config.SUBMISSION_RECORD_SHEET)
            records = sheet.get_all_records()
            result: dict[str, list] = {}
            for r in records:
                if str(r.get("날짜", ""))[:10] >= start_date:
                    name = r.get("학생", "Unknown")
                    result.setdefault(name, []).append(r)
            return result
        except Exception as e:
            logger.error("주간 데이터 조회 실패: %s", e)
            return {}

    def get_monthly_data(self, student_name: str, year: int, month: int) -> list[dict]:
        """특정 년월의 오답 이력 반환. 제출ID 앞 6자리(YYYYMM)로 필터링."""
        prefix = f"{year}{month:02d}"
        return [
            r for r in self.get_wrong_answer_history(student_name)
            if r.get("제출ID", "").startswith(prefix)
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
