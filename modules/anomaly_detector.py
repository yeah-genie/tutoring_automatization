"""
학습 이상탐지 모듈 — 포트폴리오 핵심 파트

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[이상탐지란?]

정상 패턴을 학습한 뒤, "이것과 다른" 데이터를 자동으로 찾아내는 기술.
이 프로젝트에서 "정상 패턴" = 학생의 평소 숙제 제출 경향.

활용 예시:
- 평소에 오답률 20% 수준이던 학생이 갑자기 60%가 되면 → 이상
- 항상 계산 실수만 하던 학생이 갑자기 개념 오류가 많아지면 → 이상
- 2주 넘게 숙제 제출이 없으면 → 이상

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[사용하는 알고리즘 3가지]

1. Z-score (통계적 방법, 데이터 < 5개일 때)
   - "평균에서 몇 표준편차 떨어져 있는가?"
   - |z| > 2 → 경고, |z| > 3 → 심각
   - 직관적이고 해석하기 쉬움

2. LOF — Local Outlier Factor (데이터 5~20개)
   - "이 점의 주변 밀도가 이웃들보다 훨씬 낮으면 이상"
   - 작은 데이터셋에서 강점
   - score > 1.5 → 경고, > 2.0 → 심각

3. IsolationForest (데이터 20개 이상)
   - 랜덤 트리로 데이터를 분리할 때 "빨리 고립되는" 점 = 이상
   - 큰 데이터에서 더 안정적
   - anomaly_score < -0.1 → 경고, < -0.2 → 심각

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[피처 (Feature) — 모델에 넣는 입력값]

세션 하나를 4개의 숫자로 표현:
- wrong_rate:          오답률 (0~1)
- concept_ratio:       오답 중 개념부족 비율 (0~1)
- calc_ratio:          오답 중 계산실수 비율 (0~1)
- days_since_prev:     이전 제출 이후 경과일

이 4개 숫자들의 패턴이 평소와 다르면 → 이상 감지
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np

logger = logging.getLogger(__name__)

# 알고리즘 선택 기준 세션 수
LOF_MIN_SESSIONS = 5
ISOLATION_FOREST_MIN_SESSIONS = 20


@dataclass
class AnomalyAlert:
    student_name: str
    alert_type: str       # 'wrong_rate_spike' | 'pattern_shift' | 'submission_gap'
    severity: str         # 'warning' | 'critical'
    score: float
    description: str
    recommendation: str


class AnomalyDetector:
    def __init__(self):
        # scikit-learn은 실제 세션 데이터가 있을 때만 임포트
        # (설치 안 된 환경에서도 import 오류 없이 실행되도록)
        pass

    def detect(self, student_name: str, sessions: list[dict]) -> list[AnomalyAlert]:
        """
        학생의 세션 이력을 분석해서 이상 징후 목록 반환.

        sessions: db.get_sessions() 결과 (최신순 정렬)
        최소 2개 이상의 세션이 있어야 비교 가능.
        """
        alerts = []

        if len(sessions) < 2:
            logger.debug("%s: 세션 수 부족 (%d개), 이상탐지 건너뜀", student_name, len(sessions))
            return alerts

        # ① 제출 공백 탐지 (알고리즘 불필요, 날짜 계산으로 충분)
        gap_alert = self._check_submission_gap(student_name, sessions)
        if gap_alert:
            alerts.append(gap_alert)

        # ② 오답률 + 오류 패턴 이상탐지
        features = self._extract_features(sessions)
        if features is None:
            return alerts

        n = len(features)
        logger.debug("%s: 세션 %d개로 이상탐지 실행", student_name, n)

        if n < LOF_MIN_SESSIONS:
            alerts += self._detect_zscore(student_name, features, sessions)
        elif n < ISOLATION_FOREST_MIN_SESSIONS:
            alerts += self._detect_lof(student_name, features, sessions)
        else:
            alerts += self._detect_isolation_forest(student_name, features, sessions)

        return alerts

    # ─── 알고리즘별 구현 ──────────────────────────────────────

    def _detect_zscore(
        self, student_name: str, features: np.ndarray, sessions: list[dict]
    ) -> list[AnomalyAlert]:
        """
        Z-score 방법.
        z = (현재값 - 평균) / 표준편차

        예: 평균 오답률 0.2, 표준편차 0.05 일 때
        현재 오답률 0.45 → z = (0.45-0.2)/0.05 = 5.0 → 매우 이상
        """
        alerts = []
        latest = features[-1]     # 가장 최근 세션
        history = features[:-1]   # 나머지 이력

        if len(history) < 1:
            return alerts

        mean = history.mean(axis=0)
        std = history.std(axis=0)

        # 표준편차가 0이면 비교 불가 (모든 값이 동일한 피처)
        safe_std = np.where(std < 1e-6, 1e-6, std)
        z_scores = np.abs((latest - mean) / safe_std)

        feature_names = ["오답률", "개념오류비율", "계산실수비율", "제출간격"]

        for i, (z, fname) in enumerate(zip(z_scores, feature_names)):
            if z > 3.0:
                alerts.append(self._build_alert(
                    student_name, "pattern_shift", "critical", float(z),
                    latest, sessions[-1], fname,
                    f"{fname}가 평소 대비 {z:.1f}배 벗어났습니다 (Z-score: {z:.1f})"
                ))
            elif z > 2.0:
                alerts.append(self._build_alert(
                    student_name, "pattern_shift", "warning", float(z),
                    latest, sessions[-1], fname,
                    f"{fname}가 평소보다 높습니다 (Z-score: {z:.1f})"
                ))

        return alerts

    def _detect_lof(
        self, student_name: str, features: np.ndarray, sessions: list[dict]
    ) -> list[AnomalyAlert]:
        """
        LOF (Local Outlier Factor).

        각 데이터 포인트 주변의 '밀도'를 이웃들과 비교.
        내 주변이 이웃들보다 훨씬 '듬성듬성'하면 이상치.

        LOF score 해석:
        - 약 1.0: 정상 (주변 밀도와 비슷)
        - 1.5 이상: 경고
        - 2.0 이상: 심각한 이상
        """
        try:
            from sklearn.neighbors import LocalOutlierFactor
            from sklearn.preprocessing import StandardScaler
        except ImportError:
            logger.warning("scikit-learn 미설치. Z-score로 대체합니다.")
            return self._detect_zscore(student_name, features, sessions)

        alerts = []

        # StandardScaler: 피처들의 단위(범위)를 통일. 오답률(0~1)과 제출간격(0~30일)을 같은 스케일로.
        scaler = StandardScaler()
        scaled = scaler.fit_transform(features)

        n_neighbors = min(3, len(features) - 1)
        lof = LocalOutlierFactor(n_neighbors=n_neighbors, novelty=True)
        lof.fit(scaled[:-1])  # 최근 세션 제외하고 "정상 패턴" 학습

        # 최근 세션이 얼마나 이상한지 점수 계산
        # decision_function: 음수일수록, 절댓값 클수록 이상
        score = -lof.decision_function(scaled[-1:].reshape(1, -1))[0]
        logger.debug("%s LOF score: %.3f", student_name, score)

        if score > 2.0:
            alerts.append(self._build_alert(
                student_name, "pattern_shift", "critical", score,
                features[-1], sessions[-1], "전체패턴",
                f"학습 패턴이 평소와 크게 달라졌습니다 (LOF: {score:.2f})"
            ))
        elif score > 1.5:
            alerts.append(self._build_alert(
                student_name, "pattern_shift", "warning", score,
                features[-1], sessions[-1], "전체패턴",
                f"학습 패턴에 변화가 감지됩니다 (LOF: {score:.2f})"
            ))

        return alerts

    def _detect_isolation_forest(
        self, student_name: str, features: np.ndarray, sessions: list[dict]
    ) -> list[AnomalyAlert]:
        """
        IsolationForest.

        랜덤하게 피처 하나를 골라서 랜덤한 값으로 데이터를 '분리'하는 트리를 100개 만듦.
        이상치는 적은 분리 횟수로도 고립됨 → 분리하기 쉬운 = 이상.

        contamination=0.1 → "전체 데이터의 10%는 이상일 것"이라고 가정.
        """
        try:
            from sklearn.ensemble import IsolationForest
            from sklearn.preprocessing import StandardScaler
        except ImportError:
            logger.warning("scikit-learn 미설치. Z-score로 대체합니다.")
            return self._detect_zscore(student_name, features, sessions)

        alerts = []

        scaler = StandardScaler()
        scaled = scaler.fit_transform(features)

        clf = IsolationForest(n_estimators=100, contamination=0.1, random_state=42)
        clf.fit(scaled[:-1])

        # anomaly_score: 음수 클수록 이상 (-0.5 이하면 강한 이상)
        anomaly_score = clf.decision_function(scaled[-1:].reshape(1, -1))[0]
        logger.debug("%s IsolationForest score: %.3f", student_name, anomaly_score)

        if anomaly_score < -0.2:
            alerts.append(self._build_alert(
                student_name, "pattern_shift", "critical", abs(anomaly_score),
                features[-1], sessions[-1], "전체패턴",
                f"학습 패턴 이상 감지 (IsolationForest score: {anomaly_score:.3f})"
            ))
        elif anomaly_score < -0.1:
            alerts.append(self._build_alert(
                student_name, "pattern_shift", "warning", abs(anomaly_score),
                features[-1], sessions[-1], "전체패턴",
                f"학습 패턴 변화 감지 (IsolationForest score: {anomaly_score:.3f})"
            ))

        return alerts

    # ─── 보조 메서드 ──────────────────────────────────────────

    def _check_submission_gap(
        self, student_name: str, sessions: list[dict]
    ) -> AnomalyAlert | None:
        """마지막 제출 이후 일수가 비정상적으로 긴지 확인."""
        latest_date_str = sessions[0].get("submitted_at", "")[:10]
        try:
            latest_date = datetime.strptime(latest_date_str, "%Y-%m-%d")
        except ValueError:
            return None

        days_since = (datetime.now() - latest_date).days

        if days_since >= 14:
            return AnomalyAlert(
                student_name=student_name,
                alert_type="submission_gap",
                severity="critical",
                score=float(days_since),
                description=f"마지막 제출 이후 {days_since}일 경과",
                recommendation="학생에게 숙제 제출 여부를 확인해보세요.",
            )
        elif days_since >= 7:
            return AnomalyAlert(
                student_name=student_name,
                alert_type="submission_gap",
                severity="warning",
                score=float(days_since),
                description=f"마지막 제출 이후 {days_since}일 경과",
                recommendation="다음 수업 때 숙제 진행 상황을 확인해보세요.",
            )
        return None

    def _extract_features(self, sessions: list[dict]) -> np.ndarray | None:
        """
        세션 목록 → numpy 배열 변환.
        각 세션을 [wrong_rate, concept_ratio, calc_ratio, days_since_prev] 4차원 벡터로.
        """
        rows = []
        # 날짜 계산을 위해 순서 뒤집기 (오래된 것부터)
        ordered = list(reversed(sessions))

        for i, sess in enumerate(ordered):
            if i == 0:
                days_since_prev = 0.0
            else:
                try:
                    curr = datetime.strptime(sess["submitted_at"][:10], "%Y-%m-%d")
                    prev = datetime.strptime(ordered[i-1]["submitted_at"][:10], "%Y-%m-%d")
                    days_since_prev = float((curr - prev).days)
                except ValueError:
                    days_since_prev = 0.0

            rows.append([
                float(sess.get("wrong_rate", 0.0)),
                float(sess.get("concept_ratio", 0.0)),
                float(sess.get("calc_ratio", 0.0)),
                days_since_prev,
            ])

        if not rows:
            return None
        return np.array(rows)

    @staticmethod
    def _build_alert(
        student_name: str,
        alert_type: str,
        severity: str,
        score: float,
        feature_vec: np.ndarray,
        session: dict,
        triggered_by: str,
        description: str,
    ) -> AnomalyAlert:
        wrong_rate = feature_vec[0]
        recommendations = {
            "오답률": f"오답률이 {wrong_rate*100:.0f}%입니다. 이번 수업에서 기초 개념 복습을 권장합니다.",
            "개념오류비율": "개념 이해도가 낮아 보입니다. 교과서 개념 정리부터 다시 시작해보세요.",
            "계산실수비율": "계산 실수가 잦습니다. 검산 습관을 기르도록 지도해보세요.",
            "제출간격": "제출 간격이 길어지고 있습니다. 학습 동기를 확인해보세요.",
            "전체패턴": f"전반적인 학습 패턴이 변화했습니다. 다음 수업에서 원인을 파악해보세요.",
        }
        return AnomalyAlert(
            student_name=student_name,
            alert_type=alert_type,
            severity=severity,
            score=round(score, 3),
            description=description,
            recommendation=recommendations.get(triggered_by, "다음 수업에서 확인이 필요합니다."),
        )
