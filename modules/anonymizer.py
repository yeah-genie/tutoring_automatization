"""
학생 실명을 외부 API 전송 전에 익명 ID로 치환하는 모듈.

왜 필요한가:
  Claude API 같은 외부 서버로 프롬프트를 전송할 때 실명이 포함되면
  미성년자 개인정보가 제3자 서버 로그에 남을 수 있다.
  실명 대신 STU_001 같은 익명 ID를 사용하면 이 위험을 줄일 수 있다.
"""

import config


class Anonymizer:
    def __init__(self):
        names = list(config.STUDENT_DRIVE_FOLDERS.keys())
        self._real_to_id: dict[str, str] = {
            name: f"STU_{i + 1:03d}" for i, name in enumerate(names)
        }
        self._id_to_real: dict[str, str] = {v: k for k, v in self._real_to_id.items()}

    def mask(self, name: str) -> str:
        """실명 → 익명 ID. 알 수 없는 이름은 그대로 반환."""
        return self._real_to_id.get(name, name)

    def unmask(self, anon_id: str) -> str:
        """익명 ID → 실명. 알 수 없는 ID는 그대로 반환."""
        return self._id_to_real.get(anon_id, anon_id)

    def mask_dict(self, data: dict) -> dict:
        """dict의 키(학생 이름)를 익명 ID로 치환."""
        return {self.mask(k): v for k, v in data.items()}

    def unmask_dict(self, data: dict) -> dict:
        """dict의 키(익명 ID)를 실명으로 복원."""
        return {self.unmask(k): v for k, v in data.items()}

    @property
    def mapping(self) -> dict[str, str]:
        """현재 실명→익명 매핑 반환 (디버깅용)."""
        return dict(self._real_to_id)
