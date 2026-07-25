"""
[담당: 승희] 공영주차장(공공데이터) + 민영주차장(크롤링) 통합 검색 페이지.

카카오 REST 키(지오코딩)를 쓰지 않는 구성이라, 주소/주차장명 키워드 검색으로
필터링하고 결과를 지도에 표시한다.

데이터 흐름
    공영: 서울시 공영주차장 안내 정보 CSV -> collectors/public_parking_api.py 정제
          -> PUBLIC_PARKING_LOT 적재 (종로구 정제본은 이미 완성: 종로구_공영주차장_정제.csv)
    민영: collectors/private_parking_crawler.py 크롤링 -> PRIVATE_PARKING_LOT 적재
"""

import pandas as pd
import streamlit as st

import config
from common.db import read_sql
from common.kakao_map import build_map_html
from common.ui import apply_style, hero

st.set_page_config(page_title="주차장 검색", page_icon="🅿️", layout="wide")
apply_style()
hero("🅿️", "주차장 검색", "공영·민영 주차장을 한 번에 검색하고 지도로 확인하세요. (담당: 승희)")

CATEGORY_COLOR = {"공영주차장": "#2ec4b6", "민영주차장": "#ff9f1c"}

SAMPLE_DATA = pd.DataFrame(
    [
        {"name": "샘플 공영주차장 (세종로)", "lat": 37.5734, "lng": 126.9759, "category": "공영주차장", "info": "DB 미설정 - 샘플"},
        {"name": "샘플 민영주차장 (인사동)", "lat": 37.5717, "lng": 126.9857, "category": "민영주차장", "info": "DB 미설정 - 샘플"},
    ]
)


@st.cache_data(ttl=600)
def load_public() -> pd.DataFrame:
    df = read_sql(
        "SELECT parking_name AS name, latitude AS lat, longitude AS lng, "
        "CONCAT(address, ' / ', COALESCE(fee, '요금정보없음')) AS info "
        "FROM PUBLIC_PARKING_LOT WHERE latitude IS NOT NULL"
    )
    df["category"] = "공영주차장"
    return df


@st.cache_data(ttl=600)
def load_private() -> pd.DataFrame:
    df = read_sql(
        "SELECT parking_name AS name, latitude AS lat, longitude AS lng, "
        "CONCAT(COALESCE(address, '주소 미상'), ' / ', COALESCE(fee, '요금정보없음')) AS info "
        "FROM PRIVATE_PARKING_LOT WHERE latitude IS NOT NULL"
    )
    df["category"] = "민영주차장"
    return df


def load_all() -> pd.DataFrame:
    if not config.is_db_configured():
        return SAMPLE_DATA
    frames = []
    try:
        frames.append(load_public())
    except Exception as exc:  # noqa: BLE001
        st.warning(f"공영주차장 조회 실패 (테이블 미적재?): {exc}")
    try:
        frames.append(load_private())
    except Exception as exc:  # noqa: BLE001
        st.warning(f"민영주차장 조회 실패 (테이블 미적재?): {exc}")
    if not frames:
        return SAMPLE_DATA
    return pd.concat(frames, ignore_index=True)


all_lots = load_all()
if not config.is_db_configured():
    st.info("DB 미설정 상태라 샘플 데이터를 표시합니다.")

# ── 검색/필터 ─────────────────────────────────────────────────
col_kw, col_type = st.columns([3, 1])
with col_kw:
    keyword = st.text_input("🔎 주차장명 또는 주소 키워드 (예: 종로, 세종로, 공영)")
with col_type:
    lot_types = st.multiselect(
        "주차장 구분",
        options=sorted(all_lots["category"].unique()),
        default=sorted(all_lots["category"].unique()),
    )

filtered = all_lots[all_lots["category"].isin(lot_types)]
if keyword:
    mask = filtered["name"].str.contains(keyword, na=False) | filtered["info"].str.contains(keyword, na=False)
    filtered = filtered[mask]

m1, m2, m3 = st.columns(3)
m1.metric("검색 결과", f"{len(filtered):,}곳")
m2.metric("공영", f"{(filtered['category'] == '공영주차장').sum():,}곳")
m3.metric("민영", f"{(filtered['category'] == '민영주차장').sum():,}곳")

st.write("")

if filtered.empty:
    st.warning("조건에 맞는 주차장이 없습니다. 키워드나 구분을 바꿔보세요.")
elif config.KAKAO_JS_KEY:
    map_html = build_map_html(
        filtered,
        app_key=config.KAKAO_JS_KEY,
        center_lat=filtered["lat"].mean(),
        center_lng=filtered["lng"].mean(),
        category_colors=CATEGORY_COLOR,
        level=6,
    )
    st.iframe(map_html, height=580, width="stretch")
else:
    st.warning("`.env`의 KAKAO_JS_KEY가 없어 지도를 표시할 수 없습니다.")

with st.expander("📋 데이터 표로 보기"):
    st.dataframe(
        filtered.rename(columns={"name": "주차장명", "category": "구분", "info": "상세정보"}),
        width="stretch",
        hide_index=True,
    )