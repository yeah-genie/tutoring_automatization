"""
학생 학습 현황 대시보드 — Streamlit

실행: streamlit run student_dashboard.py

로컬 SQLite DB에서 데이터를 읽으므로 API 연결 없이도 동작.
"""

import json
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

from modules.db import Database

st.set_page_config(
    page_title="수학 과외 학습 현황",
    page_icon="📚",
    layout="wide",
)

db = Database()


# ─── 사이드바 ────────────────────────────────────────────────
st.sidebar.title("📚 수학 과외 대시보드")

students = db.get_all_student_names()
if not students:
    st.warning("아직 저장된 데이터가 없습니다. main.py를 먼저 실행해주세요.")
    st.stop()

selected_student = st.sidebar.selectbox("학생 선택", students)

date_range = st.sidebar.selectbox(
    "기간",
    ["최근 1개월", "최근 3개월", "최근 6개월", "전체"],
    index=0,
)
days_map = {"최근 1개월": 30, "최근 3개월": 90, "최근 6개월": 180, "전체": 9999}
cutoff = datetime.now() - timedelta(days=days_map[date_range])

# ─── 데이터 로드 ─────────────────────────────────────────────
sessions = db.get_sessions(selected_student, limit=200)
sessions_df = pd.DataFrame(sessions) if sessions else pd.DataFrame()

if not sessions_df.empty:
    sessions_df["submitted_at"] = pd.to_datetime(sessions_df["submitted_at"])
    sessions_df = sessions_df[sessions_df["submitted_at"] >= cutoff].sort_values("submitted_at")

alerts = db.get_recent_alerts(selected_student)
alerts_df = pd.DataFrame(alerts) if alerts else pd.DataFrame()

# ─── 상단 지표 카드 ──────────────────────────────────────────
st.title(f"📊 {selected_student} 학습 현황")

col1, col2, col3, col4 = st.columns(4)

if not sessions_df.empty:
    avg_wrong = sessions_df["wrong_rate"].mean()
    total_sessions = len(sessions_df)
    latest_date = sessions_df["submitted_at"].max().strftime("%m/%d")
    recent_trend = sessions_df["wrong_rate"].tail(3).mean() - sessions_df["wrong_rate"].head(3).mean()
    trend_text = f"▲ {recent_trend*100:.1f}%" if recent_trend > 0 else f"▼ {abs(recent_trend)*100:.1f}%"
    trend_color = "normal" if recent_trend <= 0 else "inverse"
else:
    avg_wrong = total_sessions = 0
    latest_date = "—"
    trend_text = "—"
    trend_color = "normal"

col1.metric("평균 오답률", f"{avg_wrong*100:.1f}%", delta=None)
col2.metric("총 제출 횟수", f"{total_sessions}회")
col3.metric("최근 제출일", latest_date)
col4.metric("최근 추세", trend_text, delta_color=trend_color)

st.divider()

# ─── 오답률 추이 (시계열) ─────────────────────────────────────
st.subheader("📈 오답률 추이")

if not sessions_df.empty:
    chart_df = sessions_df[["submitted_at", "wrong_rate"]].copy()
    chart_df["wrong_rate_pct"] = chart_df["wrong_rate"] * 100
    chart_df = chart_df.rename(columns={"submitted_at": "날짜", "wrong_rate_pct": "오답률 (%)"})
    st.line_chart(chart_df.set_index("날짜")["오답률 (%)"])
else:
    st.info("이 기간에 데이터가 없습니다.")

# ─── 오답 유형 분포 ───────────────────────────────────────────
st.subheader("🗂 오답 유형 분포")

if not sessions_df.empty:
    type_totals: dict[str, int] = {}
    for counts_str in sessions_df["error_type_counts"]:
        counts = counts_str if isinstance(counts_str, dict) else json.loads(counts_str or "{}")
        for k, v in counts.items():
            type_totals[k] = type_totals.get(k, 0) + int(v)

    if type_totals:
        type_df = pd.DataFrame(
            {"오답 유형": list(type_totals.keys()), "건수": list(type_totals.values())}
        ).sort_values("건수", ascending=False)
        st.bar_chart(type_df.set_index("오답 유형"))
    else:
        st.info("오답 유형 데이터가 없습니다.")

st.divider()

# ─── 피처별 추이 (이상탐지 이해용) ───────────────────────────
with st.expander("🔬 상세 피처 추이 (이상탐지 입력값)"):
    st.caption(
        "이상탐지 모델이 실제로 보는 4개 숫자의 변화입니다. "
        "한 값이 갑자기 튀면 이상 감지가 발동됩니다."
    )
    if not sessions_df.empty:
        feature_df = sessions_df[["submitted_at", "wrong_rate", "concept_ratio", "calc_ratio"]].copy()
        feature_df = feature_df.rename(columns={
            "submitted_at": "날짜",
            "wrong_rate": "오답률",
            "concept_ratio": "개념오류비율",
            "calc_ratio": "계산실수비율",
        })
        st.line_chart(feature_df.set_index("날짜"))

# ─── 이상탐지 알림 로그 ───────────────────────────────────────
st.subheader("🚨 이상탐지 알림 이력")

if not alerts_df.empty:
    for _, row in alerts_df.iterrows():
        icon = "🚨" if row.get("severity") == "critical" else "⚠️"
        date_str = str(row.get("detected_at", ""))[:10]
        with st.container():
            col_a, col_b = st.columns([1, 8])
            col_a.markdown(f"### {icon}")
            col_b.markdown(
                f"**{date_str}** — {row.get('alert_type', '')}\n\n"
                f"{row.get('description', '')}\n\n"
                f"💡 {row.get('recommendation', '')}"
            )
            st.divider()
else:
    st.success("최근 이상 패턴이 감지되지 않았습니다.")

# ─── 세션 상세 테이블 ─────────────────────────────────────────
with st.expander("📋 세션 상세 데이터"):
    if not sessions_df.empty:
        display_df = sessions_df[[
            "submitted_at", "homework_title",
            "total_problems", "correct_count", "wrong_rate"
        ]].copy()
        display_df["wrong_rate"] = (display_df["wrong_rate"] * 100).round(1).astype(str) + "%"
        display_df = display_df.rename(columns={
            "submitted_at": "제출일",
            "homework_title": "숙제",
            "total_problems": "총문제",
            "correct_count": "정답",
            "wrong_rate": "오답률",
        })
        st.dataframe(display_df, use_container_width=True)

# ─── 전체 학생 비교 ───────────────────────────────────────────
st.divider()
st.subheader("👥 전체 학생 비교")

all_summaries = []
for name in students:
    s = db.get_sessions(name, limit=10)
    if s:
        df_s = pd.DataFrame(s)
        all_summaries.append({
            "학생": name,
            "평균 오답률": f"{df_s['wrong_rate'].mean()*100:.1f}%",
            "제출 횟수": len(s),
            "최근 제출": str(s[0]["submitted_at"])[:10],
        })

if all_summaries:
    st.dataframe(pd.DataFrame(all_summaries), use_container_width=True)
