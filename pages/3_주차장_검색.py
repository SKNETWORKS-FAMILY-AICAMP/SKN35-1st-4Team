"""
[담당: 승희] 공영 + 민영 주차장 통합 검색 페이지.

기능
    자치구/키워드/구분 필터 -> 예상 주차요금 계산 -> 추천 점수 정렬 -> 지도 + 목록

데이터 흐름
    수집  주차정보안내시스템 + 실시간 여유  -> collectors/seoul_parking.py
    로딩  DB -> CSV -> 즉석 수집 폴백      -> common/parking_data.py
    계산  예상요금 · 운영여부 · 추천 점수    -> common/recommend.py

DB가 없어도 data/cleaned/parking_lot.csv 로 바로 동작한다.
"""

import pandas as pd
import streamlit as st

import config
from common.geo import haversine_km
from common.kakao_map import build_map_html
from common.parking_data import load_parking_lots
from common.recommend import (
    format_availability,
    format_fee,
    format_hours,
    rank_parking_lots,
)
from common.ui import apply_style, hero

st.set_page_config(page_title="주차장 검색", page_icon="🅿️", layout="wide")
apply_style()
hero("🅿️", "주차장 검색", "공영·민영 주차장을 한 번에 검색하고 지도로 확인하세요. (담당: 승희)")

CATEGORY_COLOR = {"공영": "#2ec4b6", "민영": "#ff9f1c"}

# 수집 범위(common/parking_data.DISTRICTS)와 맞춘 기본 자치구
DEFAULT_DISTRICT = "종로구"

# 반경 검색의 기준점으로 쓸 서울 주요 지점 (카카오 REST 키가 없어 주소 검색 대신 사용)
LANDMARKS = {
    "광화문광장": (37.5720, 126.9769),
    "서울시청": (37.5663, 126.9779),
    "동대문DDP": (37.5665, 127.0092),
    "강남역": (37.4979, 127.0276),
    "홍대입구역": (37.5572, 126.9245),
    "여의도역": (37.5216, 126.9243),
    "잠실역": (37.5133, 127.1000),
}

all_lots, source_notes = load_parking_lots()

if all_lots.empty:
    st.error("주차장 데이터를 한 건도 불러오지 못했습니다. `seoul_parking.csv`가 저장소에 있는지 확인해주세요.")
    st.stop()

# ── 사이드바 검색 조건 ────────────────────────────────────────
with st.sidebar:
    st.subheader("검색 조건", divider="gray")

    districts = sorted(d for d in all_lots["district"].dropna().unique() if d != "기타")
    district_options = ["서울 전체", *districts]
    district = st.selectbox(
        "자치구",
        district_options,
        # 주차정보안내시스템 수집 범위를 종로구로 잡아둬서 기본값도 종로구로 맞춘다
        index=district_options.index(DEFAULT_DISTRICT) if DEFAULT_DISTRICT in district_options else 0,
        key="district",
    )

    keyword = st.text_input(
        "주차장명 · 주소 키워드",
        placeholder="예: 세종로, 공영, 종로3가",
        key="keyword",
    )

    categories = st.pills(
        "구분",
        sorted(all_lots["lot_category"].dropna().unique()),
        selection_mode="multi",
        default=sorted(all_lots["lot_category"].dropna().unique()),
        key="categories",
    )

    hours = st.slider("주차 예정 시간 (시간)", 0.5, 12.0, 2.0, step=0.5, key="hours")

    only_open = st.toggle("지금 운영 중인 곳만", value=True, key="only_open")
    only_free = st.toggle("무료 주차장만", value=False, key="only_free")

    st.subheader("반경 검색", divider="gray")
    center_name = st.selectbox("기준 위치", ["사용 안 함", *LANDMARKS], key="center")
    radius_km = st.slider("반경 (km)", 0.3, 5.0, 1.0, step=0.1, key="radius",
                          disabled=center_name == "사용 안 함")

    with st.expander("추천 가중치"):
        st.caption("추천순 정렬에 쓰이는 가중치입니다. 합이 1이 되도록 자동 정규화됩니다.")
        w_distance = st.slider("거리", 0.0, 1.0, 0.5, step=0.1, key="w_distance",
                               disabled=center_name == "사용 안 함")
        w_availability = st.slider("여유", 0.0, 1.0, 0.3, step=0.1, key="w_availability")
        w_fee = st.slider("요금", 0.0, 1.0, 0.2, step=0.1, key="w_fee")

# ── 필터링 ────────────────────────────────────────────────────
filtered = all_lots.copy()

if district != "서울 전체":
    filtered = filtered[filtered["district"] == district]

if categories:
    filtered = filtered[filtered["lot_category"].isin(categories)]
else:
    st.warning("구분을 하나 이상 선택해주세요.")
    filtered = filtered.iloc[0:0]

if keyword:
    haystack = filtered["parking_name"].fillna("") + " " + filtered["address"].fillna("")
    filtered = filtered[haystack.str.contains(keyword, case=False, na=False)]

if only_free:
    is_free = filtered["base_fee"].fillna(0).le(0) & filtered["add_fee"].fillna(0).le(0)
    filtered = filtered[is_free]

# 반경 검색: 기준점을 고르면 거리 계산 후 반경 안만 남긴다 (좌표 없는 곳은 자동 제외)
has_center = center_name != "사용 안 함"
if has_center:
    center_lat, center_lng = LANDMARKS[center_name]
    with_coord = filtered.dropna(subset=["latitude", "longitude"]).copy()
    with_coord["distance_km"] = with_coord.apply(
        lambda r: haversine_km(center_lat, center_lng, r["latitude"], r["longitude"]), axis=1
    )
    filtered = with_coord[with_coord["distance_km"] <= radius_km]
else:
    filtered = filtered.assign(distance_km=0.0)

# ── 예상요금 · 추천 점수 ──────────────────────────────────────
ranked = rank_parking_lots(
    filtered,
    radius_km=radius_km if has_center else 1.0,
    hours=hours,
    w_distance=w_distance if has_center else 0.0,
    w_availability=w_availability,
    w_fee=w_fee,
    only_open=only_open,
)

# ── 요약 지표 ─────────────────────────────────────────────────
metrics = st.columns(4)
metrics[0].metric("검색 결과", f"{len(ranked):,}곳")
metrics[1].metric("공영", f"{(ranked['lot_category'] == '공영').sum():,}곳")
metrics[2].metric("민영", f"{(ranked['lot_category'] == '민영').sum():,}곳")
if not ranked.empty:
    metrics[3].metric(
        f"{hours:g}시간 예상요금 (중앙값)",
        f"{ranked['estimated_fee'].median():,.0f}원",
    )
else:
    metrics[3].metric(f"{hours:g}시간 예상요금 (중앙값)", "-")

if ranked.empty:
    st.warning("조건에 맞는 주차장이 없습니다. 반경을 넓히거나 키워드·필터를 바꿔보세요.")
    with st.expander("데이터 출처"):
        st.write("\n".join(f"- {note}" for note in source_notes))
    st.stop()

# 표시용 텍스트 (요금/운영시간/여유)
ranked["요금"] = ranked.apply(format_fee, axis=1)
ranked["운영시간"] = ranked.apply(format_hours, axis=1)
ranked["여유"] = ranked.apply(format_availability, axis=1)

sort_label = st.segmented_control(
    "정렬",
    ["추천순", "요금 낮은순", "여유 많은순", "가까운순", "이름순"],
    default="추천순",
    key="sort",
    label_visibility="collapsed",
)
sort_keys = {
    "추천순": ("total_score", False),
    "요금 낮은순": ("estimated_fee", True),
    "여유 많은순": ("score_availability", False),
    "가까운순": ("distance_km", True),
    "이름순": ("parking_name", True),
}
sort_col, ascending = sort_keys.get(sort_label or "추천순", ("total_score", False))
if sort_col == "distance_km" and not has_center:
    st.caption("`가까운순`은 사이드바에서 기준 위치를 골라야 동작합니다. 추천순으로 표시합니다.")
    sort_col, ascending = "total_score", False
ranked = ranked.sort_values(sort_col, ascending=ascending).reset_index(drop=True)

# ── 지도 ──────────────────────────────────────────────────────
mappable = ranked.dropna(subset=["latitude", "longitude"])

if not config.KAKAO_JS_KEY:
    st.warning("`.env`의 KAKAO_JS_KEY가 없어 지도를 표시할 수 없습니다.")
else:
    map_df = pd.DataFrame(
        {
            "name": ranked["parking_name"],
            "lat": ranked["latitude"],
            "lng": ranked["longitude"],
            "category": ranked["lot_category"],
            "info": (
                ranked["address"].fillna("")
                + " · " + ranked["요금"]
                + " · " + ranked["운영시간"]
                + " · " + ranked["여유"]
                + f" · {hours:g}시간 예상 " + ranked["estimated_fee"].map("{:,.0f}원".format)
            ),
        }
    )

    if mappable.empty and not has_center:
        map_center = LANDMARKS["광화문광장"]
    elif mappable.empty:
        map_center = LANDMARKS[center_name]
    else:
        map_center = (mappable["latitude"].mean(), mappable["longitude"].mean())

    st.iframe(
        build_map_html(
            map_df,
            app_key=config.KAKAO_JS_KEY,
            center_lat=map_center[0],
            center_lng=map_center[1],
            category_colors=CATEGORY_COLOR,
            level=5 if has_center else 7,
        ),
        height=580,
    )
    if len(mappable) < len(ranked):
        st.caption(f"검색 결과 {len(ranked):,}곳 중 좌표가 있는 {len(mappable):,}곳만 지도에 표시됩니다.")

# ── 목록 ──────────────────────────────────────────────────────
st.subheader("검색 결과", divider="gray")

display_columns = {
    "parking_name": st.column_config.TextColumn("주차장명", width="medium"),
    "lot_category": st.column_config.TextColumn("구분", width="small"),
    "lot_type": st.column_config.TextColumn("유형", width="small"),
    "district": st.column_config.TextColumn("자치구", width="small"),
    "address": st.column_config.TextColumn("주소", width="medium"),
    "estimated_fee": st.column_config.NumberColumn(
        f"{hours:g}시간 예상요금", format="%,d원", width="small"
    ),
    "요금": st.column_config.TextColumn("요금 체계", width="medium"),
    "운영시간": st.column_config.TextColumn("운영시간", width="small"),
    "여유": st.column_config.TextColumn("주차면", width="small"),
    "total_score": st.column_config.ProgressColumn(
        "추천 점수", min_value=0.0, max_value=1.0, format="%.2f", width="small"
    ),
}
if has_center:
    display_columns["distance_km"] = st.column_config.NumberColumn(
        "거리", format="%.2f km", width="small"
    )

st.dataframe(
    ranked[[c for c in display_columns if c in ranked.columns]],
    column_config=display_columns,
    hide_index=True,
    height=420,
    key="results",
)

st.download_button(
    "검색 결과 CSV 내려받기",
    data=ranked.to_csv(index=False).encode("utf-8-sig"),
    file_name=f"주차장_검색결과_{district}_{hours:g}시간.csv",
    mime="text/csv",
)

with st.expander("데이터 출처 · 계산 방법"):
    st.write("\n".join(f"- {note}" for note in source_notes))
    st.markdown(
        f"""
        **예상요금** = 기본요금 + ⌈(주차시간 − 기본시간) ÷ 추가단위시간⌉ × 추가요금
        (일 최대요금이 있으면 상한 적용) — 지금 기준 {hours:g}시간

        **추천 점수** = 거리 점수 × {w_distance if has_center else 0:.1f}
        + 여유 점수 × {w_availability:.1f} + 요금 점수 × {w_fee:.1f} (합이 1이 되도록 정규화)

        여유 정보가 없는 주차장은 여유 점수를 0.5(중립)로 두어 불이익이 없도록 했습니다.
        """
    )
