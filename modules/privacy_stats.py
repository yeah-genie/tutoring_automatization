"""
차등 프라이버시(Differential Privacy) 통계 모듈.

왜 필요한가:
  학생 그룹 통계(평균 오답률, 주요 오류 유형 등)를 외부 리포트나
  연구 목적으로 공유할 때, 개별 학생 데이터를 역추적하지 못하도록
  수학적 노이즈를 추가한다.

핵심 개념:
  ε(엡실론) — 프라이버시 예산. 작을수록 보호 강도 높고 정확도 낮음.
    ε = 0.1 : 강한 보호 (공개 통계용)
    ε = 1.0 : 균형  (내부 분석용)
    ε = 10.0: 약한 보호 (거의 원본과 같음)
"""

import diffprivlib
import numpy as np
from modules.db import Database


class PrivacyStats:
    def __init__(self, epsilon: float = 1.0):
        self.epsilon = epsilon
        self.db = Database()

    def mean_wrong_rate(self) -> dict:
        """
        전체 학생 평균 오답률을 DP 적용해 계산.
        오답률은 0~1 범위 → sensitivity = 1/n (한 학생 제거 시 최대 변화량).
        """
        sessions = self._get_all_sessions()
        if not sessions:
            return {"raw": None, "dp": None, "epsilon": self.epsilon}

        rates = np.array([s["wrong_rate"] for s in sessions])

        raw_mean = float(np.mean(rates))

        # diffprivlib: 범위(bounds)와 epsilon 지정
        dp_mean = diffprivlib.tools.mean(
            rates,
            epsilon=self.epsilon,
            bounds=(0.0, 1.0),
        )

        return {
            "raw": round(raw_mean, 4),
            "dp": round(float(dp_mean), 4),
            "epsilon": self.epsilon,
            "n": len(rates),
        }

    def error_type_distribution(self) -> dict:
        """
        전체 오답 유형 분포를 DP 적용해 계산.
        각 카운트에 라플라스 노이즈 추가 (sensitivity = 1).
        """
        sessions = self._get_all_sessions()
        if not sessions:
            return {}

        counts: dict[str, int] = {}
        for s in sessions:
            for etype, cnt in s.get("error_type_counts", {}).items():
                counts[etype] = counts.get(etype, 0) + cnt

        if not counts:
            return {}

        # 라플라스 메커니즘: 각 카운트에 Laplace(0, sensitivity/ε) 노이즈 추가
        sensitivity = 1.0
        scale = sensitivity / self.epsilon
        rng = np.random.default_rng()

        dp_counts = {}
        for etype, cnt in counts.items():
            noise = rng.laplace(0, scale)
            dp_counts[etype] = max(0, round(cnt + noise))  # 음수 방지

        total_dp = sum(dp_counts.values()) or 1
        return {
            "raw_counts": counts,
            "dp_counts": dp_counts,
            "dp_ratios": {k: round(v / total_dp, 3) for k, v in dp_counts.items()},
            "epsilon": self.epsilon,
        }

    def _get_all_sessions(self) -> list[dict]:
        import json, sqlite3
        with sqlite3.connect(self.db.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT wrong_rate, error_type_counts FROM sessions").fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["error_type_counts"] = json.loads(d["error_type_counts"])
                result.append(d)
            return result
