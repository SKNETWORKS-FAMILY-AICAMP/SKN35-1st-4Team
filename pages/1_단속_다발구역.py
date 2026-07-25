"""
[담당: 치훈] 서울시 불법주정차 단속 정보 (data.seoul.go.kr OA-22190) 기반
단속 다발구역 분석 페이지.

데이터 흐름
    1) 데이터셋 페이지에서 분기별 CSV 다운로드 -> data/raw/
    2) uv run python collectors/enforcement_history.py  (정제 + 다발구역 집계)
    3) uv run python loaders/load_to_db.py --csv data/cleaned/enforcement_history.csv --table ENFORCEMENT_HISTORY
"""

import pandas as pd
import streamlit as st

import config
from common.db import read_sql
from common.kakao_map import build_map_html
from common.ui import apply_style, hero

st.set_page_config(page_title="단속 다발구역", page_icon="🔥", layout="wide")
apply_style()
hero("🔥", "단속 다발구역", "불법주정차 단속이 자주 발생하는 구역을 데이터로 확인하세요. (담당: 치훈)")

SAMPLE_HOTSPOTS = pd.DataFrame(
    [
        {"name": "종로구 세종로 80-1", "lat": 37.5734, "lng": 126.9759, "violation_count": 42},
        {"name": "종로구 관수동 91-4", "lat": 37.5689, "lng": 126.9966, "violation_count": 31},
        {"name": "종로구 예지동 140-1", "lat": 37.5694, "lng": 126.9999, "violation_count": 27},
    ]
)
SAMPLE_MONTHLY = pd.DataFrame(
    {"month": ["2026-04", "2026-05", "2026-06"], "violation_count": [120, 98, 135]}
)


@st.cache_data(ttl=600)
def load_hotspots(top_n: int) -> pd.DataFrame:
    """단속 건수가 많은 주소(다발구역) TOP N + 대표 좌표."""
    return read_sql(
        "SELECT address AS name, AVG(latitude) AS lat, AVG(longitude) AS lng, "
        "COUNT(*) AS violation_count "
        "FROM ENFORCEMENT_HISTORY WHERE latitude IS NOT NULL "
        "GROUP BY address ORDER BY violation_count DESC LIMIT :top_n",
        {"top_n": top_n},
    )


@st.cache_data(ttl=600)
def load_monthly_trend() -> pd.DataFrame:
    """월별 단속 건수 추이 (enforced_at 기준)."""
    return read_sql(
        "SELECT DATE_FORMAT(enforced_at, '%Y-%m') AS month, COUNT(*) AS violation_count "
        "FROM ENFORCEMENT_HISTORY WHERE enforced_at IS NOT NULL "
        "GROUP BY month ORDER BY month"
    )


top_n = st.sidebar.slider("다발구역 TOP N", min_value=5, max_value=50, value=20, step=5)

db_ok = config.is_db_configured()
if db_ok:
    try:
        hotspots = load_hotspots(top_n)
        monthly = load_monthly_trend()
    except Exception as exc:  # noqa: BLE001
        st.error(f"DB 조회 오류, 샘플 데이터로 대체합니다: {exc}")
        hotspots, monthly = SAMPLE_HOTSPOTS, SAMPLE_MONTHLY
else:
    st.info("DB 미설정 상태라 샘플 데이터를 표시합니다.")
    hotspots, monthly = SAMPLE_HOTSPOTS, SAMPLE_MONTHLY

if hotspots.empty:
    st.warning(
        "아직 적재된 단속이력 데이터가 없습니다. "
        "collectors/enforcement_history.py 실행 후 loaders/load_to_db.py로 적재해주세요."
    )
    st.stop()

# ── 요약 메트릭 ────────────────────────────────────────────────
worst = hotspots.iloc[0]
m1, m2, m3 = st.columns(3)
m1.metric("표시 중인 다발구역", f"{len(hotspots):,}곳")
m2.metric("단속 1위 구역", worst["name"])
m3.metric("1위 구역 단속 건수", f"{int(worst['violation_count']):,}건")

st.write("")

# ── 지도 ──────────────────────────────────────────────────────
if config.KAKAO_JS_KEY:
    map_df = hotspots.copy()
    map_df["category"] = "단속다발구역"
    map_df["info"] = map_df["violation_count"].map(lambda n: f"최근 단속 {int(n)}건")
    map_html = build_map_html(
        map_df,
        app_key=config.KAKAO_JS_KEY,
        center_lat=map_df["lat"].mean(),
        center_lng=map_df["lng"].mean(),
        category_colors={"단속다발구역": "#7209b7"},
        level=6,
    )
    st.iframe(map_html, height=560, width="stretch")
else:
    st.warning("`.env`의 KAKAO_JS_KEY가 없어 지도를 표시할 수 없습니다.")

st.write("")

# ── 차트 2개 ──────────────────────────────────────────────────
col_left, col_right = st.columns(2)
with col_left:
    st.subheader("다발구역 단속 건수")
    st.bar_chart(hotspots.set_index("name")["violation_count"], color="#7209b7")
with col_right:
    st.subheader("월별 단속 건수 추이")
    if monthly.empty:
        st.info("월별 집계에 사용할 enforced_at 데이터가 없습니다.")
    else:
        st.line_chart(monthly.set_index("month")["violation_count"], color="#4361ee")

with st.expander("📋 데이터 표로 보기"):
    st.dataframe(
        hotspots.rename(
            columns={"name": "주소", "lat": "위도", "lng": "경도", "violation_count": "단속 건수"}
        ),
        width="stretch",
        hide_index=True,
    )