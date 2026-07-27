"""
프로젝트 진입점 (첫 화면) — 데이터 통합 화면.

실행
    uv run streamlit run main.py

주차장 · 단속 다발구역 · 단속 CCTV를 한 지도에 겹쳐 보여주고,
"지금 내가 선 자리가 단속 위험 구역인지"를 판정한다.
    현재 위치(브라우저) 또는 좌표 직접 입력 -> 반경 안의 단속 이력·CCTV 집계 -> 등급

데이터 흐름
    주차장  collectors/seoul_parking.py -> common/parking_data.py
    위험도  ENFORCEMENT_HISTORY / CCTV_INFO -> common/risk_data.py
    계산    common/recommend.py

나머지 기능(단속 다발구역 분석, CCTV 지도, FAQ, 로그인/마이페이지)은
왼쪽 사이드바에서 선택한다.
"""

import pandas as pd
import streamlit as st

import config
from common.geo import haversine_km
from common.geolocation import browser_position, clear_position, map_drag_position
from common.auth import current_user
from common.kakao_map import (
    ICON_CAR,
    ICON_CCTV,
    ICON_MY_LOCATION,
    ICON_PARKING,
    build_map_html,
)
from common.parking_data import load_parking_lots
from common.parking_log import list_logs
from common.recommend import (
    format_availability,
    format_fee,
    format_hours,
    rank_parking_lots,
)
from common.risk_data import (
    assess_location,
    distances_m,
    expected_fine,
    build_density_grid,
    hour_profile,
    load_cctv,
    load_hotspots,
    load_slots,
    nearest_parking,
    time_advice,
    watch_detail,
)
from common.ui import apply_style, feature_card, hero, status_chip

st.set_page_config(page_title="주정차 정보 조회 시스템", page_icon="🚗", layout="wide")
apply_style()

# 이 페이지 한정 여백 조정 — 지도를 최대한 위로 끌어올린다.
# common/ui.py 의 hero()는 팀 공용이라 건드리지 않고, 여기서만 배너를 얇게 덮어쓴다.
# (다른 페이지의 배너는 원래 크기 그대로다.)
st.html(
    """
    <style>
      /* 본문 상단 여백 축소 */
      [data-testid="stMainBlockContainer"] { padding-top: 2.2rem; }

      /* 배너를 한 줄짜리 띠로 */
      .hero { padding: 13px 20px !important; margin-bottom: 12px !important;
              border-radius: 14px !important; }
      .hero h1 { display: inline; font-size: 1.15rem !important; margin: 0 !important; }
      .hero p  { display: inline; font-size: .85rem !important; margin-left: 10px !important; }
    </style>
    """
)

hero(
    "🚗",
    "주정차 제한 정보 & 주변 주차장 안내",
    "주차장과 단속 다발구역·CCTV를 한 지도에서 보고, 지금 위치가 단속 위험 구역인지 확인하세요.",
)

# 지도를 맨 위에 두기 위해 자리만 먼저 잡아둔다.
# 지도 내용은 필터·정렬·레이어 계산이 끝난 아래쪽에서 이 컨테이너에 채운다.
map_slot = st.container()

LAYER_COLOR = {
    "공영": "#2ec4b6",
    "민영": "#ff9f1c",
    "단속 다발구역": "#e63946",
    "단속 CCTV": "#7209b7",
    "내 위치": "#4361ee",
    "내 주차 기록": "#f72585",
}
LEVEL_ICON = {
    "위험": ":material/dangerous:",
    "주의": ":material/warning:",
    "기록 없음": ":material/check_circle:",
}
LEVEL_COLOR = {"위험": "red", "주의": "orange", "기록 없음": "green"}
WATCH_COLOR = {"위험": "red", "주의": "orange", "낮음": "gray"}

DEFAULT_DISTRICT = "종로구"

# 반경 검색 기준점. 수집 범위가 종로구라 종로구 지점만 둔다.
LANDMARKS = {
    "광화문광장": (37.5720, 126.9769),
    "경복궁": (37.5796, 126.9770),
    "인사동": (37.5740, 126.9856),
    "종로3가역": (37.5704, 126.9920),
    "광장시장": (37.5701, 126.9997),
    "동대문(흥인지문)": (37.5711, 127.0094),
    "혜화역(대학로)": (37.5822, 127.0019),
}

all_lots, source_notes = load_parking_lots()
hotspots, hotspot_note = load_hotspots()
cctv, cctv_note = load_cctv()
slots = load_slots()

# 로그인한 사용자의 주차 기록 (비로그인이면 조회하지 않는다)
user = current_user()
my_logs = list_logs(user["user_id"]) if user else pd.DataFrame()
source_notes = [*source_notes, hotspot_note, cctv_note]

if all_lots.empty:
    st.error(
        "주차장 데이터를 한 건도 불러오지 못했습니다. "
        "`uv run python collectors/seoul_parking.py`로 `data/cleaned/parking_lot.csv`를 만들어주세요."
    )
    st.stop()

# ── 사이드바 ──────────────────────────────────────────────────
# 컨트롤이 20개 가까이 되어 한 줄로 쌓으면 스크롤이 길어진다.
# 자주 쓰는 것(위치·레이어·검색)만 펼쳐두고 나머지는 접는다.
with st.sidebar:
    with st.expander("내 위치", expanded=True, icon=":material/my_location:"):
        # 지도에서 마커를 끌어 옮겼으면 그 좌표를 먼저 반영한다
        dragged = map_drag_position()
        if dragged:
            st.session_state["my_lat"] = dragged["lat"]
            st.session_state["my_lng"] = dragged["lng"]

        position = browser_position()
        manual = st.toggle("좌표 직접 입력", value=False, key="manual_position")

        if manual:
            lat_default = position["lat"] if position else LANDMARKS["광화문광장"][0]
            lng_default = position["lng"] if position else LANDMARKS["광화문광장"][1]
            coord = st.columns(2)
            my_lat = coord[0].number_input(
                "위도", value=float(lat_default), format="%.6f", key="my_lat"
            )
            my_lng = coord[1].number_input(
                "경도", value=float(lng_default), format="%.6f", key="my_lng"
            )
            position = {"lat": my_lat, "lng": my_lng, "accuracy": None}
        elif position and st.button(
            "위치 지우기", icon=":material/close:", width="stretch"
        ):
            clear_position()
            st.rerun()

        risk_radius_m = st.slider("위험 판정 반경 (m)", 50, 500, 100, step=50, key="risk_radius")

    with st.expander("지도 레이어", expanded=True, icon=":material/layers:"):
        # 데이터가 없는 레이어는 아예 선택지에서 빼고 아래에 안내만 남긴다
        # (비활성 토글을 늘어놓는 것보다 깔끔하다)
        layer_options = ["주차장"]
        if not cctv.empty:
            layer_options.append("단속 CCTV")
        if not hotspots.empty:
            layer_options.append("단속 다발구역")
        if not my_logs.empty:
            layer_options.append("내 주차 기록")

        active_layers = st.pills(
            "표시할 레이어",
            layer_options,
            selection_mode="multi",
            default=layer_options,
            label_visibility="collapsed",
            key="layers",
        ) or []

        show_parking = "주차장" in active_layers
        show_cctv = "단속 CCTV" in active_layers
        show_area = "단속 다발구역" in active_layers
        show_logs = "내 주차 기록" in active_layers

        missing = []
        if cctv.empty:
            missing.append("CCTV → `collectors/cctv_api.py`")
        if hotspots.empty:
            missing.append("다발구역 → `collectors/enforcement_history_api.py`")
        if missing:
            st.caption("아직 없는 데이터: " + " · ".join(missing))
        if user is None:
            st.caption("로그인하면 내 주차 기록도 지도에 표시됩니다.")

        if show_area:
            cell_m = st.select_slider(
                "다발구역 격자 크기",
                options=[100, 150, 200, 300, 500],
                value=150,
                format_func=lambda v: f"{v}m",
                key="cell_m",
            )
            top_ratio = st.select_slider(
                "표시 범위",
                options=[0.10, 0.25, 0.50, 1.00],
                value=0.25,
                format_func=lambda v: f"단속 상위 {v:.0%}" if v < 1 else "전체 구역",
                key="top_ratio",
                help="단속 건수가 많은 칸부터 몇 %까지 칠할지",
            )
        else:
            cell_m, top_ratio = 150, 0.25

    with st.expander("검색 조건", expanded=True, icon=":material/filter_list:"):
        districts = sorted(d for d in all_lots["district"].dropna().unique() if d != "기타")
        district_options = ["서울 전체", *districts]
        district = st.selectbox(
            "자치구",
            district_options,
            index=district_options.index(DEFAULT_DISTRICT)
            if DEFAULT_DISTRICT in district_options
            else 0,
            key="district",
        )

        keyword = st.text_input(
            "주차장명 · 주소 키워드", placeholder="예: 세종로, 공영, 종로3가", key="keyword"
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

    with st.expander("반경 검색", icon=":material/radar:"):
        center_options = (["내 위치"] if position else []) + ["사용 안 함", *LANDMARKS]
        center_name = st.selectbox("기준 위치", center_options, key="center")
        radius_km = st.slider(
            "반경 (km)", 0.3, 5.0, 1.0, step=0.1, key="radius",
            disabled=center_name == "사용 안 함",
        )

    with st.expander("추천 가중치", icon=":material/tune:"):
        st.caption("추천순 정렬에 쓰입니다. 합이 1이 되도록 자동 정규화됩니다.")
        w_distance = st.slider(
            "거리", 0.0, 1.0, 0.5, step=0.1, key="w_distance",
            disabled=center_name == "사용 안 함",
        )
        w_availability = st.slider("여유", 0.0, 1.0, 0.3, step=0.1, key="w_availability")
        w_fee = st.slider("요금", 0.0, 1.0, 0.2, step=0.1, key="w_fee")

# ── 과태료 팝업 ───────────────────────────────────────────────
@st.dialog("여기 세우면 얼마?", width="small")
def show_fine_dialog(fine: dict, cheapest: dict | None) -> None:
    """예상 과태료를 크게 보여주고 합법 주차장 요금과 나란히 비교한다.

    금액을 겁주는 장치가 아니라 '주차장이 훨씬 싸다'를 눈으로 보여주는 장치다.
    """
    st.html(
        f"""
        <style>
        @keyframes fine-pop {{
            0%   {{ transform: scale(.4) rotate(-8deg); opacity: 0; }}
            60%  {{ transform: scale(1.15) rotate(3deg); opacity: 1; }}
            100% {{ transform: scale(1) rotate(0); opacity: 1; }}
        }}
        @keyframes coin-fall {{
            0%   {{ transform: translateY(-30px); opacity: 0; }}
            30%  {{ opacity: 1; }}
            100% {{ transform: translateY(90px); opacity: 0; }}
        }}
        .fine-wrap {{ text-align:center; padding: 10px 0 4px; position:relative; overflow:hidden; }}
        .fine-amt {{
            font-size: 46px; font-weight: 800; color:#e63946; letter-spacing:-1px;
            animation: fine-pop .55s cubic-bezier(.22,1.2,.36,1) both;
        }}
        .fine-sub {{ color:#6b7280; font-size:13px; margin-top:2px; }}
        .coin {{
            position:absolute; top:0; font-size:20px;
            animation: coin-fall 1.6s ease-in infinite;
        }}
        </style>
        <div class="fine-wrap">
          <span class="coin" style="left:12%; animation-delay:.0s">🪙</span>
          <span class="coin" style="left:32%; animation-delay:.4s">💸</span>
          <span class="coin" style="left:62%; animation-delay:.8s">🪙</span>
          <span class="coin" style="left:84%; animation-delay:.2s">💸</span>
          <div class="fine-amt">{fine["amount"]:,}원</div>
          <div class="fine-sub">불법주정차 과태료 (승용차 일반 구역)</div>
        </div>
        """
    )

    if cheapest:
        saving = fine["amount"] - cheapest["fee"]
        st.success(
            f"**{cheapest['name']}** 은(는) {cheapest['hours']:g}시간에 "
            f"**{cheapest['fee']:,}원** · 도보 {cheapest['walk']}분\n\n"
            f"주차장을 쓰면 **{saving:,}원** 아낍니다.",
            icon=":material/savings:",
        )

    st.caption("구역별 과태료")
    st.dataframe(
        pd.DataFrame(
            [{"구역": name, "과태료": amount, "설명": desc} for name, amount, desc in fine["table"]]
        ),
        column_config={"과태료": st.column_config.NumberColumn("과태료", format="%,d원")},
        hide_index=True,
    )
    st.caption(fine["note"])


# ── 내 위치 단속 위험 판정 ────────────────────────────────────
# 위치를 안 잡으면 이 블록이 통째로 안 보여서 기능이 있는지도 모른다.
# 그래서 미설정일 때도 안내 카드와 "여기로 미리 보기"를 띄운다.
st.subheader("내 위치 단속 위험")

if position is None:
    with st.container(border=True):
        st.markdown("**위치를 정하면 그 자리의 단속 위험을 판정합니다.**")
        st.caption(
            "사이드바 → 내 위치 에서 `현재 위치 가져오기`를 누르거나 좌표를 직접 입력하세요. "
            "GPS는 브라우저 보안 정책상 localhost·HTTPS에서만 동작합니다."
        )
        preview = st.selectbox(
            "또는 아래 지점으로 바로 확인해 보세요",
            ["선택 안 함", *LANDMARKS],
            key="preview_spot",
        )
        if preview != "선택 안 함":
            spot = LANDMARKS[preview]
            position = {"lat": spot[0], "lng": spot[1], "accuracy": None}

if position:
    if hotspots.empty and cctv.empty:
        st.warning(
            "단속 이력·CCTV 데이터가 아직 없어 판정할 수 없습니다. "
            "`collectors/cctv_api.py` 와 `collectors/enforcement_history_api.py` 를 먼저 실행해주세요.",
            icon=":material/database_off:",
        )
    else:
        risk = assess_location(
            position["lat"], position["lng"], hotspots, cctv, radius_m=risk_radius_m
        )

        # 과태료 팝업에서 "주차장이 이만큼 싸다"를 보여주기 위한 최저가 후보
        cheapest_alt = None
        near_lots = nearest_parking(position["lat"], position["lng"], all_lots, limit=5)
        if not near_lots.empty:
            priced = rank_parking_lots(
                near_lots.assign(distance_km=near_lots["distance_m"] / 1000),
                radius_km=1.0, hours=hours, only_open=False,
            )
            if not priced.empty:
                best = priced.nsmallest(1, "estimated_fee").iloc[0]
                cheapest_alt = {
                    "name": str(best["parking_name"]),
                    "fee": int(best["estimated_fee"]),
                    "hours": hours,
                    "walk": max(1, round(float(best["distance_m"]) / 70)),
                }

        # 전체 폭 경고창 대신 카드 하나로 묶는다 (등급 + 근거 수치가 한 덩어리로 읽힌다)
        with st.container(border=True):
            verdict, stats = st.columns([2, 3], vertical_alignment="center")

            with verdict:
                st.badge(
                    risk["level"],
                    icon=LEVEL_ICON[risk["level"]],
                    color=LEVEL_COLOR[risk["level"]],
                )
                st.markdown(f"**{risk['message']}**")
                if risk["nearest_hotspot"] and risk["nearest_hotspot_m"] is not None:
                    st.caption(
                        f"가장 가까운 다발구역 · {risk['nearest_hotspot']} "
                        f"({risk['nearest_hotspot_m']:,.0f}m)"
                    )

                fine = expected_fine(risk["level"])
                if fine["show"] and st.button(
                    f"과태료 {fine['amount']:,}원 확인",
                    icon=":material/receipt_long:",
                    type="primary",
                    key="fine_button",
                ):
                    show_fine_dialog(fine, cheapest_alt)

            with stats:
                # 칸이 좁아 라벨·값을 짧게 쓰고 자세한 설명은 help(물음표)로 뺀다
                cells = st.columns(3)
                cells[0].metric(
                    "단속", f"{risk['enforcement_count']:,}건",
                    help=f"반경 {risk['radius_m']}m 안의 누적 단속 건수", border=True,
                )
                cells[1].metric(
                    "CCTV",
                    f"{risk['nearest_cctv_m']:,.0f}m" if risk["nearest_cctv_m"] is not None else "-",
                    help="가장 가까운 단속 CCTV까지 직선거리", border=True,
                )
                cells[2].metric(
                    "오차",
                    f"±{position['accuracy']:,.0f}m" if position.get("accuracy") else "수동",
                    help="브라우저가 알려준 위치 오차 (직접 입력이면 '수동')", border=True,
                )

        # 감시 유형별 상세 — CCTV(상시 촬영)와 순찰 단속은 대응이 다르다
        watches = watch_detail(
            position["lat"], position["lng"], hotspots, cctv, radius_m=risk_radius_m
        )
        if watches:
            watch_cols = st.columns(len(watches))
            for col, watch in zip(watch_cols, watches):
                with col, st.container(border=True):
                    st.markdown(f"{watch['icon']} **{watch['type']}**")
                    st.badge(watch["level"], color=WATCH_COLOR[watch["level"]])
                    st.caption(watch["summary"])
                    st.write(watch["action"])

        # 시간대별 단속 패턴 — "언제까지 괜찮나"에 답한다
        profile = hour_profile(
            position["lat"], position["lng"], slots, radius_m=risk_radius_m
        )
        advice = time_advice(profile)
        if advice:
            st.markdown("**이 구역 단속 집중 시간대**")

            # 시간대는 "언제 피하면 되나"가 아니라 "얼마나 자주 단속되는 곳인가"를
            # 보여주는 근거다. 뜸한 시간대를 안전하다고 말하지 않는다.
            if advice["is_busy"]:
                st.error(
                    f"지금({advice['now_hour']}시)이 이 구역 단속이 가장 몰리는 시간대입니다 "
                    f"— 누적 {advice['now_count']:,}건. 즉시 주차장을 이용하세요.",
                    icon=":material/priority_high:",
                )
            else:
                st.caption(
                    f"이 구역은 {advice['peak_hour']}시 전후에 단속이 집중됩니다. "
                    f"지금 시간대 기록은 {advice['now_count']:,}건이지만, "
                    "단속 여부와 관계없이 주정차 금지 구역은 언제나 위반입니다."
                )

            chart = pd.DataFrame({"단속 건수": profile})
            chart.index.name = "시"
            st.bar_chart(chart, height=180, color="#e63946")
            st.caption(
                f"반경 {risk_radius_m}m 누적 {advice['total']:,}건 · "
                f"최다 시간대 {advice['peak_hour']}시 ({advice['peak_count']:,}건)"
            )

        if True:
            alternatives = nearest_parking(position["lat"], position["lng"], all_lots, limit=3)
            if not alternatives.empty:
                st.caption("여기 대신 세울 수 있는 가까운 합법 주차장")
                st.dataframe(
                    alternatives[["parking_name", "lot_category", "address", "distance_m"]],
                    column_config={
                        "parking_name": st.column_config.TextColumn("주차장명", width="medium"),
                        "lot_category": st.column_config.TextColumn("구분", width="small"),
                        "address": st.column_config.TextColumn("주소", width="medium"),
                        "distance_m": st.column_config.NumberColumn("거리", format="%,d m"),
                    },
                    hide_index=True,
                )

    st.caption(
        "과거 단속 기록과 CCTV 위치를 기준으로 한 **참고 정보**입니다. "
        "기록이 없다고 주차 가능한 곳이라는 뜻은 아니며, 현장 표지판과 노면 표시를 반드시 확인하세요."
    )
    st.space("small")

# ── 주차장 필터링 ─────────────────────────────────────────────
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

has_center = center_name != "사용 안 함"
if has_center:
    if center_name == "내 위치":
        center_lat, center_lng = position["lat"], position["lng"]
    else:
        center_lat, center_lng = LANDMARKS[center_name]
    with_coord = filtered.dropna(subset=["latitude", "longitude"]).copy()
    with_coord["distance_km"] = with_coord.apply(
        lambda r: haversine_km(center_lat, center_lng, r["latitude"], r["longitude"]), axis=1
    )
    filtered = with_coord[with_coord["distance_km"] <= radius_km]
else:
    filtered = filtered.assign(distance_km=0.0)

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
st.subheader("주차장 검색")

metrics = st.columns(4)
metrics[0].metric("검색 결과", f"{len(ranked):,}곳", border=True)
metrics[1].metric("공영", f"{(ranked['lot_category'] == '공영').sum():,}곳", border=True)
metrics[2].metric("민영", f"{(ranked['lot_category'] == '민영').sum():,}곳", border=True)
metrics[3].metric(
    f"{hours:g}시간 예상요금",
    f"{ranked['estimated_fee'].median():,.0f}원" if not ranked.empty else "-",
    help="검색 결과의 중앙값", border=True,
)

if ranked.empty:
    st.warning("조건에 맞는 주차장이 없습니다. 반경을 넓히거나 키워드·필터를 바꿔보세요.",
               icon=":material/search_off:")
    with st.expander("데이터 출처", icon=":material/info:"):
        st.write("\n".join(f"- {note}" for note in source_notes))
    st.stop()

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

# ── 통합 지도 ─────────────────────────────────────────────────
def _markers(df, name_col, category, info_series, details=None):
    """build_map_html이 요구하는 컬럼으로 변환.

    info는 말풍선 제목 아래 회색 한 줄(주소 등),
    details는 그 아래 '라벨 - 값' 행 목록이다. 예전처럼 한 줄에 ·로 이어붙이면
    말풍선 폭이 좁아 줄바꿈이 어긋나서 읽기 나쁘다.
    """
    out = pd.DataFrame(
        {
            "name": df[name_col].astype(str),
            "lat": df["latitude"],
            "lng": df["longitude"],
            "category": category,
            "info": info_series,
        }
    )
    out["details"] = pd.Series(
        details if details is not None else [[] for _ in range(len(out))], index=out.index
    )
    return out


# 다발구역은 점 마커 대신 격자 폴리곤으로 칠한다 (kakao.maps.Polygon)
area_polygons = (
    build_density_grid(
        hotspots, cell_m=cell_m, top_ratio=top_ratio, weight_col="violation_count"
    )
    if show_area and not hotspots.empty
    else []
)

# 나중에 넣은 레이어가 지도에서 위에 그려진다.
# CCTV(196개)를 먼저 깔고 주차장을 얹어야 주차장이 가려지지 않는다. 내 위치가 맨 위.
layers = []

if show_cctv and not cctv.empty:
    purpose = (
        cctv["purpose"].fillna("불법주정차 단속")
        if "purpose" in cctv.columns
        else pd.Series("불법주정차 단속", index=cctv.index)
    )
    layers.append(
        _markers(
            cctv, "address", "단속 CCTV",
            pd.Series("", index=cctv.index),
            details=[
                [["관리", str(org)], ["용도", str(use)]]
                for org, use in zip(cctv["organization"].fillna("기관 미상"), purpose)
            ],
        )
    )

if show_parking:
    hour_label = f"{hours:g}시간"
    layers.append(
        _markers(
            ranked, "parking_name", ranked["lot_category"],
            ranked["address"].fillna("주소 미상"),
            details=[
                [
                    ["요금", fee_text],
                    ["운영", open_text],
                    ["주차면", avail_text],
                    [hour_label, estimated],
                ]
                for fee_text, open_text, avail_text, estimated in zip(
                    ranked["요금"],
                    ranked["운영시간"],
                    ranked["여유"],
                    ranked["estimated_fee"].map("{:,.0f}원".format),
                )
            ],
        )
    )

if show_logs and not my_logs.empty:
    mine = my_logs.dropna(subset=["latitude", "longitude"]).copy()
    if not mine.empty:
        layers.append(
            _markers(
                mine, "place", "내 주차 기록",
                mine["address"].fillna(""),
                details=[
                    [
                        ["일시", parked.strftime("%Y-%m-%d %H:%M")],
                        ["요금", "유료" if charged else "무료"],
                        ["메모", memo if isinstance(memo, str) and memo else "-"],
                    ]
                    for parked, charged, memo in zip(
                        mine["parked_at"], mine["is_charged"], mine["memo"]
                    )
                ],
            )
        )

if position:
    layers.append(
        pd.DataFrame(
            [{
                "name": "내 위치",
                "lat": position["lat"],
                "lng": position["lng"],
                "category": "내 위치",
                "info": "",
                "details": [
                    ["좌표", f"{position['lat']:.5f}, {position['lng']:.5f}"],
                    ["정확도",
                     f"±{position['accuracy']:,.0f}m" if position.get("accuracy") else "직접 입력"],
                ],
            }]
        )
    )

map_df = pd.concat(layers, ignore_index=True) if layers else pd.DataFrame(
    columns=["name", "lat", "lng", "category", "info", "details"]
)
mappable = map_df.dropna(subset=["lat", "lng"])

# 지도는 화면 맨 위(map_slot)에 그린다. 계산은 여기서 다 끝난 뒤라야 하므로
# 미리 잡아둔 자리에 나중에 채워 넣는 방식을 쓴다.
with map_slot:
    # 지도(왼쪽) + 목록 패널(오른쪽). 목록에서 고르면 그 지점으로 지도가 이동한다.
    map_area, list_area = st.columns([3, 1], gap="small")

    with list_area:
        st.markdown("**목록**")
        kinds = ["전체", *dict.fromkeys(mappable["category"])] if not mappable.empty else ["전체"]
        kind = st.selectbox("구분", kinds, label_visibility="collapsed", key="list_kind")
        place_query = st.text_input(
            "장소 검색", placeholder="이름·주소 검색",
            label_visibility="collapsed", key="list_query",
        )

        listed = mappable.copy()
        if kind != "전체":
            listed = listed[listed["category"] == kind]
        if place_query:
            hay = listed["name"].fillna("") + " " + listed["info"].fillna("")
            listed = listed[hay.str.contains(place_query, case=False, na=False)]

        # 내 위치가 있으면 가까운 순으로 정렬해 목록이 바로 쓸모 있게 한다
        if position and not listed.empty:
            listed = listed.assign(
                _d=distances_m(position["lat"], position["lng"], listed.rename(
                    columns={"lat": "latitude", "lng": "longitude"}))
            ).sort_values("_d")

        st.caption(f"{len(listed):,}건")
        picked = st.dataframe(
            listed[["name", "info"]].rename(columns={"name": "이름", "info": "주소"}),
            column_config={
                "이름": st.column_config.TextColumn("이름", width="medium"),
                "주소": st.column_config.TextColumn("주소", width="small"),
            },
            hide_index=True,
            height=470,
            selection_mode="single-row",
            on_select="rerun",
            key="place_list",
        )

    selected_place = None
    rows = picked.selection.rows if picked is not None and hasattr(picked, "selection") else []
    if rows and not listed.empty and rows[0] < len(listed):
        chosen = listed.iloc[rows[0]]
        selected_place = (float(chosen["lat"]), float(chosen["lng"]), str(chosen["name"]))

    if not config.KAKAO_JS_KEY:
        st.warning("`.env`의 KAKAO_JS_KEY가 없어 지도를 표시할 수 없습니다.")
    elif mappable.empty and not area_polygons:
        st.info("표시할 레이어가 없습니다. 사이드바에서 레이어를 켜주세요.")
    else:
        if selected_place:
            map_center = (selected_place[0], selected_place[1])
        elif position:
            map_center = (position["lat"], position["lng"])
        elif has_center:
            map_center = (center_lat, center_lng)
        elif not mappable.empty:
            map_center = (mappable["lat"].mean(), mappable["lng"].mean())
        else:
            pts = [pt for poly in area_polygons for pt in poly["path"]]
            map_center = (
                sum(p[0] for p in pts) / len(pts),
                sum(p[1] for p in pts) / len(pts),
            )

        map_ctx = map_area if config.KAKAO_JS_KEY else st.container()
        map_ctx.iframe(
            build_map_html(
                mappable,
                app_key=config.KAKAO_JS_KEY,
                center_lat=map_center[0],
                center_lng=map_center[1],
                category_colors={
                    **{k: v for k, v in LAYER_COLOR.items() if k in set(mappable["category"])},
                    **({"단속 다발구역": LAYER_COLOR["단속 다발구역"]} if area_polygons else {}),
                },
                level=3 if selected_place else (4 if position else (5 if has_center else 7)),
                polygons=area_polygons,
                category_icons={
                    "공영": ICON_PARKING,
                    "민영": ICON_PARKING,
                    "단속 CCTV": ICON_CCTV,
                    "내 주차 기록": ICON_CAR,
                    "내 위치": ICON_MY_LOCATION,
                },
                pulse_categories={"내 위치"},
                draggable_category="내 위치",
                focus=(
                    {
                        "lat": position["lat"],
                        "lng": position["lng"],
                        "radius_m": risk_radius_m,
                        "color": LAYER_COLOR["내 위치"],
                    }
                    if position
                    else None
                ),
            ),
            height=580,
        )
        if selected_place:
            map_area.caption(f"목록에서 선택: **{selected_place[2]}**")
        elif position:
            map_area.caption("지도의 파란 :material/my_location: 마커를 끌어서 위치를 옮길 수 있습니다.")
        parts = [f"{k} {v:,}개" for k, v in mappable["category"].value_counts().items()]
        if area_polygons:
            parts.append(f"단속 다발구역 {len(area_polygons):,}칸({cell_m}m 격자)")
        map_area.caption(" · ".join(parts))

# ── 목록 ──────────────────────────────────────────────────────
with st.container(horizontal=True, vertical_alignment="center"):
    st.subheader("검색 결과 목록", width="stretch")
    st.download_button(
        "CSV 내려받기",
        data=ranked.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"주차장_검색결과_{district}_{hours:g}시간.csv",
        mime="text/csv",
        icon=":material/download:",
        width="content",
    )

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

with st.expander("데이터 출처 · 계산 방법", icon=":material/info:"):
    st.write("\n".join(f"- {note}" for note in source_notes))
    st.markdown(
        f"""
        **예상요금** = 기본요금 + ⌈(주차시간 − 기본시간) ÷ 추가단위시간⌉ × 추가요금
        (일 최대요금이 있으면 상한 적용) — 지금 기준 {hours:g}시간

        **추천 점수** = 거리 점수 × {w_distance if has_center else 0:.1f}
        + 여유 점수 × {w_availability:.1f} + 요금 점수 × {w_fee:.1f} (합이 1이 되도록 정규화)

        **단속 위험 등급** — 반경 {risk_radius_m}m 안의 누적 단속 건수와 가장 가까운 CCTV 거리로 판정
        · 위험: 단속 10건 이상 또는 CCTV 50m 이내
        · 주의: 단속 1건 이상 또는 CCTV 150m 이내
        · 기록 없음: 둘 다 해당 없음
        """
    )
    
