"""
중복 파일 감지 모듈.
1단계: MD5 해시 (완전 동일한 파일)
2단계: 지각적 해시 (같은 답안지를 다르게 찍은 사진)

상태 저장은 modules/db.py (SQLite) 가 담당.
"""

import hashlib
import logging
from pathlib import Path
from typing import Optional, Tuple

import imagehash
from PIL import Image

from modules.db import Database

logger = logging.getLogger(__name__)

PERCEPTUAL_HASH_THRESHOLD = 10


class DuplicateChecker:
    def __init__(self, db: Database):
        self.db = db

    def is_duplicate(self, file_path: Path, student_name: str) -> Tuple[bool, str]:
        """Returns (is_duplicate, reason)."""
        md5 = self._md5(file_path)

        existing = self.db.get_hash(md5)
        if existing:
            return True, f"완전 동일한 파일 (원본: {existing['student_name']} / {existing['filename']})"

        phash = self._phash(file_path)
        if phash is not None:
            for entry in self.db.get_all_phashes():
                if not entry["phash"]:
                    continue
                stored = imagehash.hex_to_hash(entry["phash"])
                distance = phash - stored
                if distance <= PERCEPTUAL_HASH_THRESHOLD:
                    return True, f"유사한 이미지 (유사도 거리: {distance}, 원본: {entry['student_name']} / {entry['filename']})"

        return False, ""

    def register(self, file_path: Path, student_name: str):
        md5 = self._md5(file_path)
        phash = self._phash(file_path)
        self.db.register_hash(
            md5=md5,
            phash=str(phash) if phash is not None else None,
            student_name=student_name,
            filename=file_path.name,
        )
        logger.debug("등록 완료: %s", file_path.name)

    @staticmethod
    def _md5(file_path: Path) -> str:
        h = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _phash(file_path: Path) -> Optional[imagehash.ImageHash]:
        try:
            return imagehash.phash(Image.open(file_path))
        except Exception:
            return None
