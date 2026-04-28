"""
SQLite 로컬 데이터베이스 모듈.

기존 JSON 파일 두 개(.processed_rows.json, .file_hashes.json)를 대체하고,
이상탐지에 필요한 세션 데이터도 여기에 저장합니다.

왜 SQLite인가?
- JSON 파일은 나중에 pandas로 분석하기 불편함
- SQLite는 pandas.read_sql()로 바로 DataFrame 변환 가능
- 나중에 "이번 달 오답률 상위 학생" 같은 집계도 SQL로 한 줄
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

import config


SCHEMA = """
-- 처리된 구글폼 행 추적 (기존 .processed_rows.json 역할)
CREATE TABLE IF NOT EXISTS processed_rows (
    row_number  INTEGER PRIMARY KEY,
    student_name TEXT,
    processed_at TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'success'
    -- status: 'success' | 'failed' | 'skipped'
);

-- 파일 해시 저장 (기존 .file_hashes.json 역할)
CREATE TABLE IF NOT EXISTS file_hashes (
    md5           TEXT PRIMARY KEY,
    phash         TEXT,
    student_name  TEXT NOT NULL,
    filename      TEXT NOT NULL,
    registered_at TEXT NOT NULL
);

-- 숙제 제출 세션 요약 (이상탐지 피처 계산 기반)
CREATE TABLE IF NOT EXISTS sessions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    student_name        TEXT NOT NULL,
    homework_title      TEXT NOT NULL,
    submitted_at        TEXT NOT NULL,       -- YYYY-MM-DD
    total_problems      INTEGER DEFAULT 0,
    correct_count       INTEGER DEFAULT 0,
    wrong_rate          REAL DEFAULT 0.0,    -- wrong / total (0~1)
    concept_ratio       REAL DEFAULT 0.0,    -- 개념부족 / wrong (0~1)
    calc_ratio          REAL DEFAULT 0.0,    -- 계산실수 / wrong (0~1)
    understanding_ratio REAL DEFAULT 0.0,    -- 문제이해 / wrong (0~1)
    error_type_counts   TEXT DEFAULT '{}'    -- JSON: {"개념부족": 2, ...}
);

-- 이상탐지 결과 로그
CREATE TABLE IF NOT EXISTS anomaly_alerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    student_name    TEXT NOT NULL,
    detected_at     TEXT NOT NULL,
    alert_type      TEXT NOT NULL,   -- 'wrong_rate_spike' | 'pattern_shift' | 'submission_gap'
    severity        TEXT NOT NULL,   -- 'warning' | 'critical'
    score           REAL,            -- 이상 점수 (높을수록 이상)
    description     TEXT,
    recommendation  TEXT,
    session_id      INTEGER REFERENCES sessions(id)
);
"""


class Database:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or config.DB_PATH
        self._init_db()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # dict-like 접근 가능
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    # ─── processed_rows ──────────────────────────────────────

    def is_processed(self, row_number: int) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM processed_rows WHERE row_number = ? AND status = 'success'",
                (row_number,),
            ).fetchone()
            return row is not None

    def mark_processed(self, row_number: int, student_name: str = "", status: str = "success"):
        now = datetime.now().isoformat()
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO processed_rows (row_number, student_name, processed_at, status) VALUES (?, ?, ?, ?)",
                (row_number, student_name, now, status),
            )

    def get_failed_rows(self) -> list[int]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT row_number FROM processed_rows WHERE status = 'failed'"
            ).fetchall()
            return [r["row_number"] for r in rows]

    # ─── file_hashes ─────────────────────────────────────────

    def get_hash(self, md5: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM file_hashes WHERE md5 = ?", (md5,)
            ).fetchone()
            return dict(row) if row else None

    def get_all_phashes(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT phash, student_name, filename FROM file_hashes WHERE phash IS NOT NULL"
            ).fetchall()
            return [dict(r) for r in rows]

    def register_hash(self, md5: str, phash: str | None, student_name: str, filename: str):
        now = datetime.now().isoformat()
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO file_hashes (md5, phash, student_name, filename, registered_at) VALUES (?, ?, ?, ?, ?)",
                (md5, phash, student_name, filename, now),
            )

    # ─── sessions ────────────────────────────────────────────

    def save_session(
        self,
        student_name: str,
        homework_title: str,
        submitted_at: str,
        total_problems: int,
        correct_count: int,
        error_type_counts: dict,
    ) -> int:
        wrong = total_problems - correct_count
        wrong_rate = wrong / total_problems if total_problems > 0 else 0.0
        concept_ratio = error_type_counts.get("개념부족", 0) / wrong if wrong > 0 else 0.0
        calc_ratio = error_type_counts.get("계산실수", 0) / wrong if wrong > 0 else 0.0
        understanding_ratio = error_type_counts.get("문제이해", 0) / wrong if wrong > 0 else 0.0

        with self._conn() as conn:
            cursor = conn.execute(
                """INSERT INTO sessions
                   (student_name, homework_title, submitted_at, total_problems, correct_count,
                    wrong_rate, concept_ratio, calc_ratio, understanding_ratio, error_type_counts)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    student_name, homework_title, submitted_at,
                    total_problems, correct_count,
                    wrong_rate, concept_ratio, calc_ratio, understanding_ratio,
                    json.dumps(error_type_counts, ensure_ascii=False),
                ),
            )
            return cursor.lastrowid

    def get_sessions(self, student_name: str, limit: int = 50) -> list[dict]:
        """학생의 세션 이력 (최신순)."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM sessions WHERE student_name = ?
                   ORDER BY submitted_at DESC LIMIT ?""",
                (student_name, limit),
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["error_type_counts"] = json.loads(d["error_type_counts"])
                result.append(d)
            return result

    def get_all_student_names(self) -> list[str]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT student_name FROM sessions ORDER BY student_name"
            ).fetchall()
            return [r["student_name"] for r in rows]

    # ─── anomaly_alerts ──────────────────────────────────────

    def save_alert(
        self,
        student_name: str,
        alert_type: str,
        severity: str,
        score: float,
        description: str,
        recommendation: str,
        session_id: int | None = None,
    ):
        now = datetime.now().isoformat()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO anomaly_alerts
                   (student_name, detected_at, alert_type, severity, score, description, recommendation, session_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (student_name, now, alert_type, severity, score, description, recommendation, session_id),
            )

    def get_recent_alerts(self, student_name: str = None, limit: int = 20) -> list[dict]:
        with self._conn() as conn:
            if student_name:
                rows = conn.execute(
                    "SELECT * FROM anomaly_alerts WHERE student_name = ? ORDER BY detected_at DESC LIMIT ?",
                    (student_name, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM anomaly_alerts ORDER BY detected_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]

    def to_dataframe(self, table: str):
        """pandas DataFrame으로 변환 (대시보드/분석용)."""
        import pandas as pd
        with sqlite3.connect(self.db_path) as conn:
            return pd.read_sql(f"SELECT * FROM {table}", conn)

    # ─── 데이터 생애주기 관리 ─────────────────────────────────

    def purge_old_data(self, retention_days: int = 365) -> dict[str, int]:
        """
        보존 기간(기본 1년)이 지난 데이터를 삭제한다.

        왜 필요한가:
          GDPR 제5조(c)는 개인정보를 목적 달성 후 더 이상 보관하지 말 것을 요구.
          과외 종료 후 학습 데이터를 무한정 보관하면 법적 의무 위반이 될 수 있다.

        Returns:
          삭제된 행 수 요약 dict
        """
        cutoff = (datetime.now() - timedelta(days=retention_days)).isoformat()
        deleted: dict[str, int] = {}

        with self._conn() as conn:
            for table, col in [
                ("sessions", "submitted_at"),
                ("anomaly_alerts", "detected_at"),
                ("file_hashes", "registered_at"),
                ("processed_rows", "processed_at"),
            ]:
                cursor = conn.execute(
                    f"DELETE FROM {table} WHERE {col} < ?", (cutoff,)
                )
                deleted[table] = cursor.rowcount

        return deleted

    def delete_student_data(self, student_name: str) -> dict[str, int]:
        """
        특정 학생의 모든 데이터를 삭제한다 (잊혀질 권리).

        왜 필요한가:
          GDPR 제17조는 정보 주체(또는 법정대리인)가 요청하면
          모든 개인정보를 지체 없이 삭제할 의무를 부여한다.
          과외 종료 시 부모/학생의 삭제 요청에 대응하기 위한 기능.

        Returns:
          삭제된 행 수 요약 dict
        """
        deleted: dict[str, int] = {}

        with self._conn() as conn:
            for table in ("sessions", "anomaly_alerts", "file_hashes", "processed_rows"):
                cursor = conn.execute(
                    f"DELETE FROM {table} WHERE student_name = ?", (student_name,)
                )
                deleted[table] = cursor.rowcount

        return deleted

    def get_data_summary(self) -> dict:
        """
        현재 저장된 데이터 현황을 반환한다.
        어떤 학생의 데이터가 얼마나 오래됐는지 파악하는 데 사용.
        """
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT student_name,
                          COUNT(*) as session_count,
                          MIN(submitted_at) as oldest,
                          MAX(submitted_at) as latest
                   FROM sessions
                   GROUP BY student_name
                   ORDER BY latest DESC"""
            ).fetchall()
            return [dict(r) for r in rows]
