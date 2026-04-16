"""
중복 파일 감지 모듈.
1단계: MD5 해시 (완전 동일한 파일)
2단계: 지각적 해시 (같은 답안지를 다르게 찍은 사진)
"""

import hashlib
import json
import logging
from pathlib import Path

import imagehash
from PIL import Image

logger = logging.getLogger(__name__)

PERCEPTUAL_HASH_THRESHOLD = 10  # 해밍 거리 기준 (낮을수록 엄격)


class DuplicateChecker:
    def __init__(self, hashes_file: str):
        self.hashes_file = Path(hashes_file)
        self.data: dict = self._load()

    def _load(self) -> dict:
        if self.hashes_file.exists():
            with open(self.hashes_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"md5": {}, "phash": []}

    def _save(self):
        with open(self.hashes_file, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def _md5(self, file_path: Path) -> str:
        h = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def _phash(self, file_path: Path) -> imagehash.ImageHash | None:
        try:
            return imagehash.phash(Image.open(file_path))
        except Exception:
            return None

    def is_duplicate(self, file_path: Path, student_name: str) -> tuple[bool, str]:
        """
        Returns (is_duplicate, reason).
        중복이면 True와 이유 문자열 반환.
        """
        md5 = self._md5(file_path)

        if md5 in self.data["md5"]:
            original = self.data["md5"][md5]
            return True, f"완전 동일한 파일 (원본: {original['student']} / {original['file']})"

        phash = self._phash(file_path)
        if phash is not None:
            for entry in self.data["phash"]:
                stored = imagehash.hex_to_hash(entry["hash"])
                distance = phash - stored
                if distance <= PERCEPTUAL_HASH_THRESHOLD:
                    return True, f"유사한 이미지 (유사도 거리: {distance}, 원본: {entry['student']} / {entry['file']})"

        return False, ""

    def register(self, file_path: Path, student_name: str):
        """중복이 아닌 파일을 해시 저장소에 등록."""
        md5 = self._md5(file_path)
        self.data["md5"][md5] = {"student": student_name, "file": file_path.name}

        phash = self._phash(file_path)
        if phash is not None:
            self.data["phash"].append({
                "hash": str(phash),
                "student": student_name,
                "file": file_path.name,
            })

        self._save()
        logger.debug("등록 완료: %s (MD5: %s)", file_path.name, md5)
