"""
[담당: 종원] 서울시 불법주정차/전용차로 위반 단속 CCTV 위치정보
(data.seoul.go.kr OA-20471) 지도 페이지.

데이터 흐름
    1) collectors/cctv_api.py로 수집 (서울 열린데이터광장 Open API,
       SEOUL_OPENAPI_KEY 발급 필요 - .env 주석 참고)
    2) uv run python loaders/load_to_db.py --csv data/cleaned/cctv_info.csv --table CCTV_INFO
"""

import pandas as pd
import streamlit as st

import config
from common.db import read_sql
from common.kakao_map import build_map_html
from common.ui import apply_style, hero

st.set_page_config(page_title="CCTV 지도", page_icon="📷", layout="wide")
apply_style()
hero("📷", "단속 CCTV 지도", "불법주정차·전용차로 위반 단속 CCTV 위치를 확인하세요. (담당: 종원)")

SAMPLE_DATA = pd.DataFrame(
    [
        {"name": "샘플 CCTV (세종대로)", "lat": 37.5665, "lng": 126.9780, "category": "CCTV", "info": "DB 미설정 - 샘플 데이터"},
        {"name": "샘플 CCTV (종로2가)", "lat": 37.5700, "lng": 126.9880, "category": "CCTV", "info": "DB 미설정 - 샘플 데이터"},
    ]
)


@st.cache_data(ttl=600)
def load_cctv() -> pd.DataFrame:
    df = read_sql(
        "SELECT address AS name, latitude AS lat, longitude AS lng, "
        "COALESCE(organization, '관리기관 미상') AS info "
        "FROM CCTV_INFO WHERE latitude IS NOT NULL"
    )
    df["category"] = "CCTV"
    return df


if not config.is_db_configured():
    st.info("DB 미설정 상태라 샘플 데이터를 표시합니다.")
    df = SAMPLE_DATA
else:
    try:
        df = load_cctv()
    except Exception as exc:  # noqa: BLE001
        st.error(f"DB 조회 오류, 샘플 데이터로 대체합니다: {exc}")
        df = SAMPLE_DATA

if df.empty:
    st.warning(
        "아직 적재된 CCTV 데이터가 없습니다. "
        "collectors/cctv_api.py 실행 후 loaders/load_to_db.py로 적재해주세요."
    )
    st.stop()

# ── 주소 키워드 필터 (지오코딩 없이 텍스트 검색) ─────────────────
keyword = st.text_input("🔎 주소 키워드로 필터 (예: 종로, 세종대로)")
filtered = df[df["name"].str.contains(keyword, na=False)] if keyword else df

m1, m2 = st.columns(2)
m1.metric("전체 CCTV", f"{len(df):,}대")
m2.metric("필터 결과", f"{len(filtered):,}대")

st.write("")

if filtered.empty:
    st.warning("검색 결과가 없습니다. 키워드를 바꿔보세요.")
elif config.KAKAO_JS_KEY:
    map_html = build_map_html(
        filtered,
        app_key=config.KAKAO_JS_KEY,
        center_lat=filtered["lat"].mean(),
        center_lng=filtered["lng"].mean(),
        category_colors={"CCTV": "#e63946"},
        level=6,
    )
    st.iframe(map_html, height=600, width="stretch")
else:
    st.warning("`.env`의 KAKAO_JS_KEY가 없어 지도를 표시할 수 없습니다.")

with st.expander("📋 데이터 표로 보기"):
    st.dataframe(
        filtered.rename(columns={"name": "설치 주소", "lat": "위도", "lng": "경도", "info": "관리기관"}),
        width="stretch",
        hide_index=True,
    )