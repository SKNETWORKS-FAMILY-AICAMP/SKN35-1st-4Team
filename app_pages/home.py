"""
앗차차! — 진입점(첫 화면).

실행
    uv run streamlit run main.py

주차장 · 단속 다발구역 · 단속 CCTV를 한 지도에 겹쳐 보여주고,
"지금 내가 선 자리가 단속 위험 구역인지"를 판정한다.
    현재 위치(브라우저) 또는 좌표 직접 입력 -> 반경 안의 단속 이력·CCTV 집계 -> 등급

화면 순서
    히어로 -> 지도(+목록) -> 절약 배너 -> 위험 판정 -> 주차장 검색 -> 결과 목록
    지도와 배너는 st.container() 로 자리만 먼저 잡고, 계산이 끝난 아래쪽에서 채운다.

데이터 흐름 (전부 TiDB)
    주차장  PARKING_LOT          -> common/parking_data.py
    위험도  ENFORCEMENT_HISTORY / CCTV_INFO -> common/risk_data.py
    계산    common/recommend.py

톤
    불법주정차를 부추기지 않는다. "언제 단속을 피할 수 있나"가 아니라
    "여기 세우면 얼마고, 주차장을 쓰면 얼마를 아끼나"를 보여준다.

나머지 기능(단속 다발구역 분석, CCTV 지도, FAQ, 로그인/마이페이지)은
왼쪽 사이드바에서 선택한다.
"""

import pandas as pd
import streamlit as st

import config
from common.db import DataSourceError
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
    build_heat_blobs,
    hour_profile,
    load_cctv,
    load_hotspots,
    load_slots,
    nearest_parking,
    time_advice,
    watch_detail,
)
from common.ui import (
    AMBER,
    BLUE,
    GREEN,
    PINK,
    PURPLE,
    RED,
    MARK_ALERT,
    empty_state,
    hero,
    risk_gauge,
    safe_banner,
    section,
    savings_banner,
    savings_report,
    map_legend,
    parking_cards,
    footer,
)


# 이 페이지 한정 여백 조정 — 지도를 최대한 위로 끌어올린다.
# hero() 는 팀 공용이라 건드리지 않고, 여기서만 배너를 얇게 덮어쓴다.
# (다른 페이지의 배너는 원래 크기 그대로다.)
st.html(
    """
    <style>
      /* 상단 툴바(60px)에 배너가 가리지 않을 만큼만 여백을 준다.
         2.2rem(35px)로 줄였더니 히어로 윗부분이 툴바 뒤로 잘려 들어갔다. */
      [data-testid="stMainBlockContainer"] { padding-top: 4.4rem; }
    </style>
    """
)

# 배너에 실제 데이터 개수를 알약으로 붙이고 싶은데, 그 숫자는 아래에서 읽는다.
# 그래서 자리만 먼저 잡고 나중에 채운다 (지도·절약 배너도 같은 방식).
hero_slot = st.container()
map_slot = st.container()
# 지도 바로 아래 '앗차차! 얼마 아껴요' 배너 자리 (위험 판정이 끝나면 채운다)
banner_slot = st.container()

LAYER_COLOR = {
    "공영": GREEN,
    "민영": AMBER,
    "단속 다발구역": RED,
    "단속 CCTV": PURPLE,
    "내 위치": BLUE,
    "내 주차 기록": PINK,
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

# DB를 쓰기로 해놓고 못 읽으면 여기서 멈춘다. 예전처럼 CSV로 조용히 넘어가면
# 화면은 멀쩡한데 실제로는 옛 데이터를 보여주게 되어, 그게 더 위험하다.
try:
    all_lots, source_notes = load_parking_lots()
    hotspots, hotspot_note = load_hotspots()
    cctv, cctv_note = load_cctv()
    slots = load_slots()
except DataSourceError as exc:
    st.error(str(exc), icon=":material/database_off:")
    st.caption(
        f"접속 대상: {config.MYSQL_USER}@{config.MYSQL_HOST}:{config.MYSQL_PORT}"
        f"/{config.MYSQL_DATABASE}"
    )
    st.stop()

# 로그인한 사용자의 주차 기록 (비로그인이면 조회하지 않는다)
user = current_user()
my_logs = list_logs(user["user_id"]) if user else pd.DataFrame()
source_notes = [*source_notes, hotspot_note, cctv_note]

with hero_slot:
    hero(
        MARK_ALERT,
        "앗차차! 여기 세워도 될까?",
        "지금 자리가 단속 위험 구역인지 확인하고, 가까운 합법 주차장을 바로 찾으세요.",
        chips=[
            f"주차장 <b>{len(all_lots):,}</b>곳",
            f"단속 기록 <b>{int(hotspots['violation_count'].sum()):,}</b>건"
            if not hotspots.empty else "단속 기록 없음",
            f"단속 CCTV <b>{len(cctv):,}</b>대",
        ],
    )

if all_lots.empty:
    if config.is_db_configured():
        st.error(
            "DB의 PARKING_LOT 테이블이 비어 있습니다. "
            "`uv run python loaders/load_all.py`로 적재해주세요.",
            icon=":material/database_off:",
        )
    else:
        st.error(
            "주차장 데이터를 한 건도 불러오지 못했습니다. "
            "`uv run python collectors/seoul_parking.py`로 "
            "`data/cleaned/parking_lot.csv`를 만들어주세요."
        )
    st.stop()

# ── 사이드바 ──────────────────────────────────────────────────
# 컨트롤이 20개 가까이 되어 한 줄로 쌓으면 스크롤이 길어진다.
# 자주 쓰는 것(위치·레이어·검색)만 펼쳐두고 나머지는 접는다.

# 필터를 이것저것 만지다 결과가 0건이 되면 어디를 되돌려야 할지 알기 어렵다.
# '조건 초기화' 한 번으로 기본값으로 되돌린다.
#
# 값이 있는 위젯은 pop() 하지 않고 기본값을 직접 넣는다. text_input 은 key 를
# 지워도 화면에 입력한 글자가 그대로 남아서, "필터는 풀렸는데 검색창에는
# 키워드가 보이는" 상태가 된다. 대입해야 화면 값까지 같이 되돌아간다.
FILTER_DEFAULTS = {
    "district": DEFAULT_DISTRICT,
    "keyword": "",
    "hours": 2.0,
    "only_open": True,
    "only_free": False,
    "sort": "추천순",
    "list_query": "",
    "top_ratio": 0.25,
    "risk_radius": 100,
}

# 선택지가 데이터에 따라 달라지는 것들(있는 자치구·레이어만 노출)은
# 기본값을 여기서 알 수 없다. 지우면 위젯이 자기 default 로 다시 그려진다.
FILTER_RESET_KEYS = ("categories", "layers")


def reset_filters() -> None:
    for key, value in FILTER_DEFAULTS.items():
        st.session_state[key] = value
    for key in FILTER_RESET_KEYS:
        st.session_state.pop(key, None)


# 사이드바는 운전 중에도 쓸 수 있어야 해서 컨트롤을 셋으로 줄였다.
#   1) 내 위치   2) 지도에 표시할 것   3) 주차장 찾기
# 나머지(판정 반경·격자·가중치 등)는 기본값이 대부분 맞으므로 '고급'으로 접어둔다.
with st.sidebar:
    st.markdown("**내 위치**")
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
    elif position and st.button("위치 지우기", icon=":material/close:", width="stretch"):
        clear_position()
        st.rerun()

    st.markdown("**지도에 표시**")
    # 데이터가 없는 레이어는 아예 선택지에서 뺀다 (비활성 토글을 늘어놓는 것보다 깔끔)
    layer_options = ["주차장"]
    if not hotspots.empty:
        layer_options.append("단속 다발구역")
    if not cctv.empty:
        layer_options.append("단속 CCTV")
    if not my_logs.empty:
        layer_options.append("내 주차 기록")

    # CCTV 196대를 처음부터 켜두면 마커가 지도를 덮어 주차장이 안 보인다.
    # 가장 가까운 CCTV 거리는 아래 위험 카드가 숫자로 알려주므로,
    # 지도 위 점은 필요할 때만 켜도록 기본에서 뺀다.
    default_layers = [name for name in layer_options if name != "단속 CCTV"]
    active_layers = st.pills(
        "표시할 레이어",
        layer_options,
        selection_mode="multi",
        default=default_layers,
        label_visibility="collapsed",
        key="layers",
    ) or []

    show_parking = "주차장" in active_layers
    show_cctv = "단속 CCTV" in active_layers
    show_area = "단속 다발구역" in active_layers
    show_logs = "내 주차 기록" in active_layers

    # DB가 안 붙으면 주차장(CSV 폴백)만 뜨고 단속·CCTV 레이어가 통째로 사라진다.
    # 화면만 봐서는 "데이터가 원래 없나" 싶으니 원인을 분명히 알려준다.
    if not config.is_db_configured() or not config.KAKAO_JS_KEY:
        st.warning(
            "설정이 덜 됐습니다. 배포 환경이라면 "
            "**Manage app → ⋮ → Settings → Secrets** 에 값을 넣어주세요.",
            icon=":material/key_off:",
        )
        # 값은 절대 보여주지 않고, 어느 항목이 어디서 왔는지만 표로 확인시킨다.
        with st.expander("설정 진단", icon=":material/troubleshoot:"):
            st.dataframe(
                pd.DataFrame(config.settings_report()),
                column_config={
                    "설정됨": st.column_config.CheckboxColumn("설정됨", width="small"),
                },
                hide_index=True,
            )
            st.caption(
                "출처가 `없음` 인 항목이 아직 전달되지 않은 값입니다. "
                "비밀번호나 키 값 자체는 표시하지 않습니다."
            )

    if user is None:
        st.caption("로그인하면 내 주차 기록도 지도에 표시됩니다.")

    st.markdown("**주차장 찾기**")
    keyword = st.text_input(
        "이름·주소 검색", placeholder="예: 세종로, 공영, 종로3가",
        key="keyword", label_visibility="collapsed",
    )
    hours = st.slider("주차 예정 시간 (시간)", 0.5, 12.0, 2.0, step=0.5, key="hours")
    only_free = st.toggle("무료 주차장만", value=False, key="only_free")

    with st.expander("고급", icon=":material/tune:"):
        st.caption("기본값 그대로 써도 됩니다.")
        risk_radius_m = st.slider(
            "위험 판정 반경 (m)", 50, 500, 100, step=50, key="risk_radius",
            help="이 반경 안의 단속 기록과 CCTV로 위험도를 판정합니다.",
        )
        only_open = st.toggle("지금 운영 중인 곳만", value=True, key="only_open")

        districts = sorted(d for d in all_lots["district"].dropna().unique() if d != "기타")
        district_options = ["서울 전체", *districts]
        district = st.selectbox(
            "자치구", district_options,
            index=district_options.index(DEFAULT_DISTRICT)
            if DEFAULT_DISTRICT in district_options else 0,
            key="district",
        )
        categories = st.pills(
            "구분",
            sorted(all_lots["lot_category"].dropna().unique()),
            selection_mode="multi",
            default=sorted(all_lots["lot_category"].dropna().unique()),
            key="categories",
        )
        top_ratio = st.select_slider(
            "다발구역 표시 범위",
            options=[0.10, 0.25, 0.50, 1.00],
            value=0.25,
            format_func=lambda v: f"단속 상위 {v:.0%}" if v < 1 else "전체 구역",
            key="top_ratio",
        )

    # 반경 검색·추천 가중치는 컨트롤이 많아 없앴다. 내 위치가 있으면 그 자리를
    # 기준으로 1km 안에서 거리·여유·요금을 5:3:2로 보고 추천한다(예전 기본값).
    center_name = "내 위치" if position else "사용 안 함"
    radius_km = 1.0
    w_distance, w_availability, w_fee = 0.5, 0.3, 0.2
    cell_m = 150

    st.button(
        "조건 초기화",
        icon=":material/restart_alt:",
        width="stretch",
        on_click=reset_filters,
        help="검색·레이어 조건을 기본값으로 되돌립니다 (내 위치는 유지).",
    )

# ── 구역별 과태료 팝업 ────────────────────────────────────────
# 금액을 크게 보여주는 연출은 지도 아래 배너(common/ui.py savings_banner)로 옮겼다.
# 팝업은 "구역마다 얼마나 다른가"를 더 알고 싶을 때만 여는 보조 화면이다.
@st.dialog("앗차차! 구역마다 과태료가 다릅니다", width="small")
def show_fine_dialog(fine: dict, cheapest: dict | None) -> None:
    if cheapest:
        saving = fine["amount"] - cheapest["fee"]
        st.success(
            f"**{cheapest['name']}** 은(는) {cheapest['hours']:g}시간에 "
            f"**{cheapest['fee']:,}원** · 도보 {cheapest['walk']}분\n\n"
            f"주차장을 쓰면 **{saving:,}원** 아낍니다.",
            icon=":material/savings:",
        )

    st.dataframe(
        pd.DataFrame(
            [{"구역": name, "과태료": amount, "설명": desc} for name, amount, desc in fine["table"]]
        ),
        column_config={"과태료": st.column_config.NumberColumn("과태료", format="%,d원")},
        hide_index=True,
    )
    st.caption(fine["note"])


# ── 누적 절약 리포트 ──────────────────────────────────────────
# 주차 기록 한 건 = "그때 불법주차 대신 주차장을 골랐다"로 보고 과태료만큼을
# 아낀 것으로 센다. 실제 지출을 뺀 순이익이 아니라, 습관을 칭찬하는 지표다.
if not my_logs.empty:
    savings_report(len(my_logs), len(my_logs) * expected_fine("위험")["amount"])

# ── 내 위치 단속 위험 판정 ────────────────────────────────────
# 위치를 안 잡으면 이 블록이 통째로 안 보여서 기능이 있는지도 모른다.
# 그래서 미설정일 때도 안내 카드와 "여기로 미리 보기"를 띄운다.
section("여기 세워도 될까?", "위치를 정하면 그 자리의 단속 위험과 대안 주차장을 알려드려요")

if position is None:
    # 위젯을 그리기 전에 이전 선택을 먼저 읽는다. 위젯 반환값만 보면
    # "지점을 골랐는데도 '위치를 정하세요' 안내가 그대로 남는" 상태가 된다.
    picked_spot = st.session_state.get("preview_spot")

    with st.container(border=True):
        if not picked_spot:
            empty_state(
                "sign_car",
                "여기 세워도 되는 자리일까요?",
                "위치를 정하면 그 자리의 단속 위험과 예상 과태료를 알려드려요.",
            )

        if picked_spot:
            st.markdown(f"**{picked_spot}** 기준으로 판정하고 있습니다.")
            st.caption(
                "사이드바 → 내 위치 에서 `현재 위치 가져오기`를 누르면 실제 내 자리로 바뀝니다. "
                "아래에서 다른 지점을 고르거나, 같은 지점을 다시 눌러 해제할 수 있습니다."
            )
        else:
            st.markdown("**위치를 정하면 그 자리의 단속 위험을 판정합니다.**")
            st.caption(
                "사이드바 → 내 위치 에서 `현재 위치 가져오기`를 누르거나 좌표를 직접 입력하세요. "
                "GPS는 브라우저 보안 정책상 localhost·HTTPS에서만 동작합니다."
            )

        # 셀렉트박스는 한 번 열어야 뭐가 있는지 보인다. 지점이 7곳뿐이라
        # 전부 펼쳐두는 pills 가 "눌러보면 되는구나"를 더 빨리 알려준다.
        preview = st.pills(
            "둘러볼 지점" if picked_spot else "또는 아래 지점으로 바로 확인해 보세요",
            list(LANDMARKS),
            key="preview_spot",
        )

    if preview:
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

        # "주차장이 이만큼 싸다"를 보여주기 위한 최저가 후보.
        #
        # 배너는 "N원 아껴요"라고 금액을 단언하므로, 요금 정보가 실제로 있는 곳만
        # 후보로 삼는다. 원본에 요금이 안 실린 주차장(base_fee 결측)은 계산상 0원이
        # 되어버려서, 그대로 쓰면 절약액이 실제보다 부풀려진다.
        # (예: '관수(민영)' 은 base_fee/add_fee 가 전부 NaN → 2시간 0원으로 잡힌다)
        cheapest_alt = None
        near_lots = nearest_parking(position["lat"], position["lng"], all_lots, limit=12)
        priced_known = near_lots[near_lots["base_fee"].notna()] if not near_lots.empty else near_lots
        if not priced_known.empty:
            priced = rank_parking_lots(
                priced_known.assign(distance_km=priced_known["distance_m"] / 1000),
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

        # ── 지도 바로 아래 배너 ──
        # 예전에는 버튼을 눌러야 팝업으로 보였는데, 한 번 닫으면 다시 안 보여서
        # 정작 중요한 금액 비교를 놓쳤다. 지금은 위치를 잡는 순간 항상 보인다.
        fine = expected_fine(risk["level"])
        with banner_slot:
            if fine["show"]:
                savings_banner(
                    fine["amount"],
                    lot_name=cheapest_alt["name"] if cheapest_alt else None,
                    lot_fee=cheapest_alt["fee"] if cheapest_alt else None,
                    hours=hours,
                    walk_min=cheapest_alt["walk"] if cheapest_alt else None,
                )
            else:
                safe_banner(
                    "이 자리는 단속 기록이 없습니다.",
                    "기록이 없다고 주차 가능한 곳이라는 뜻은 아닙니다. "
                    "현장 표지판과 노면 표시를 꼭 확인하세요.",
                )

        # 전체 폭 경고창 대신 카드 하나로 묶는다 (등급 + 근거 수치가 한 덩어리로 읽힌다)
        with st.container(border=True):
            gauge, verdict, stats = st.columns([1.1, 2, 3], vertical_alignment="center")

            with gauge:
                # 배지만으로는 '위험'과 '주의'의 정도 차이가 안 느껴진다.
                # 바늘 각도로 얼마나 심한지를 같이 보여준다.
                risk_gauge(risk["level"], f"반경 {risk['radius_m']}m 기준")

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

                if fine["show"] and st.button(
                    "구역별 과태료 보기",
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
            st.bar_chart(chart, height=180, color=RED)
            st.caption(
                f"반경 {risk_radius_m}m 누적 {advice['total']:,}건 · "
                f"최다 시간대 {advice['peak_hour']}시 ({advice['peak_count']:,}건)"
            )

        # 경고만 하고 끝내면 갈 곳이 없다. 항상 대안을 같이 띄운다.
        alternatives = nearest_parking(position["lat"], position["lng"], all_lots, limit=3)
        if not alternatives.empty:
            st.markdown("**여기 대신 세울 수 있는 가까운 합법 주차장**")
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

if position:
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
out_of_area = False
if has_center:
    if center_name == "내 위치":
        center_lat, center_lng = position["lat"], position["lng"]
    else:
        center_lat, center_lng = LANDMARKS[center_name]
    with_coord = filtered.dropna(subset=["latitude", "longitude"]).copy()
    with_coord["distance_km"] = with_coord.apply(
        lambda r: haversine_km(center_lat, center_lng, r["latitude"], r["longitude"]), axis=1
    )
    near = with_coord[with_coord["distance_km"] <= radius_km]

    # 수집 범위가 종로구뿐이라, 다른 동네에서 위치를 잡으면 반경 1km 안에
    # 주차장이 하나도 없다. 그때 빈 목록을 주면 "왜 아무것도 없지?" 가 되므로
    # 반경을 풀고 가까운 순으로 보여주면서 범위 밖이라고 알려준다.
    if near.empty and not with_coord.empty:
        out_of_area = True
        filtered = with_coord.nsmallest(30, "distance_km")
    else:
        filtered = near
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
section("가까운 주차장", "조건에 맞는 합법 주차장을 요금·거리 기준으로 골라드려요")

metrics = st.columns(4)
metrics[0].metric("검색 결과", f"{len(ranked):,}곳", border=True)
metrics[1].metric("공영", f"{(ranked['lot_category'] == '공영').sum():,}곳", border=True)
metrics[2].metric("민영", f"{(ranked['lot_category'] == '민영').sum():,}곳", border=True)
metrics[3].metric(
    f"{hours:g}시간 예상요금",
    f"{ranked['estimated_fee'].median():,.0f}원" if not ranked.empty else "-",
    help="검색 결과의 중앙값", border=True,
)

if out_of_area:
    st.info(
        f"현재 위치는 수집 범위({DEFAULT_DISTRICT}) 밖입니다. "
        "반경 제한을 풀고 **가까운 순으로** 보여드립니다.",
        icon=":material/travel_explore:",
    )

# 결과가 없어도 st.stop() 하지 않는다.
# 지도는 맨 위 map_slot 에 '나중에' 채워지는데, 여기서 멈추면 그 코드까지
# 도달하지 못해 지도가 통째로 사라진다 (위치를 잡는 순간 지도가 없어지던 원인).
no_results = ranked.empty
if no_results:
    st.warning(
        "조건에 맞는 주차장이 없습니다. 키워드·필터를 바꿔보세요. "
        "사이드바 맨 아래 `조건 초기화`로 한 번에 되돌릴 수 있습니다.",
        icon=":material/search_off:",
    )
    sort_label = "추천순"
else:
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


# 다발구역은 점 마커도 격자 사각형도 아닌 '번지는 원'으로 그린다.
# 집계 값은 격자와 같고 모양만 원이라, 인접한 구역끼리 겹쳐 열지도처럼 읽힌다.
area_blobs = (
    build_heat_blobs(
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

if show_parking and not no_results:
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
        # 목록의 '구분' 셀렉트박스는 사이드바 레이어 pills 와 하는 일이 겹쳐서 없앴다.
        # 남은 건 검색 하나 — 고를 게 적어야 운전 중에도 쓴다.
        place_query = st.text_input(
            "장소 검색", placeholder="이름·주소 검색",
            label_visibility="collapsed", key="list_query",
        )

        listed = mappable.copy()
        if place_query:
            hay = listed["name"].fillna("") + " " + listed["info"].fillna("")
            listed = listed[hay.str.contains(place_query, case=False, na=False)]

        # 내 위치가 있으면 가까운 순으로 정렬해 목록이 바로 쓸모 있게 한다
        if position and not listed.empty:
            listed = listed.assign(
                _d=distances_m(position["lat"], position["lng"], listed.rename(
                    columns={"lat": "latitude", "lng": "longitude"}))
            ).sort_values("_d")
            shown = listed.assign(거리=(listed["_d"] / 1000).round(2))[
                ["name", "거리"]
            ].rename(columns={"name": "이름"})
            columns = {
                "이름": st.column_config.TextColumn("이름", width="medium"),
                "거리": st.column_config.NumberColumn("거리", format="%.2f km", width="small"),
            }
        else:
            shown = listed[["name", "info"]].rename(columns={"name": "이름", "info": "주소"})
            columns = {
                "이름": st.column_config.TextColumn("이름", width="medium"),
                "주소": st.column_config.TextColumn("주소", width="small"),
            }

        st.caption(f"{len(listed):,}건 · 누르면 지도가 이동합니다")
        picked = st.dataframe(
            shown,
            column_config=columns,
            hide_index=True,
            height=560,
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
        # 배포판에는 .env 가 없다. 어디에 넣어야 하는지를 환경에 맞게 알려준다.
        st.warning(
            "KAKAO_JS_KEY가 없어 지도를 표시할 수 없습니다. "
            "배포 환경이라면 **Manage app → Settings → Secrets** 에, "
            "로컬이라면 `.env` 에 넣어주세요.",
            icon=":material/map:",
        )
    elif mappable.empty and not area_blobs:
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
            map_center = (
                sum(b["lat"] for b in area_blobs) / len(area_blobs),
                sum(b["lng"] for b in area_blobs) / len(area_blobs),
            )

        # 사이드바에도 같은 버튼이 있지만, 사이드바를 접고 지도만 보는 사용자가
        # 위치를 잡으려고 다시 열지 않아도 되게 지도 바로 위에 하나 더 둔다.
        locate_col, hint_col = map_area.columns([1.1, 2.9], vertical_alignment="center")
        with locate_col:
            browser_position(key="geolocation_map", rerun_if_late=True)
        with hint_col:
            st.caption(
                "버튼을 누르면 내 위치로 이동합니다. 지도의 파란 마커를 끌어도 옮겨져요."
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
                    **({"단속 다발구역": LAYER_COLOR["단속 다발구역"]} if area_blobs else {}),
                },
                level=3 if selected_place else (4 if position else (5 if has_center else 7)),
                blobs=area_blobs,
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
            height=620,
        )
        if selected_place:
            map_area.caption(f"목록에서 선택: **{selected_place[2]}**")
        elif position:
            map_area.caption("지도의 파란 :material/my_location: 마커를 끌어서 위치를 옮길 수 있습니다.")
        # 지도 위 색이 뭘 뜻하는지 글로 설명하면 잘 안 읽힌다. 색 견본을 같이 둔다.
        counts = mappable["category"].value_counts().to_dict()
        legend_items = [
            (LAYER_COLOR[name], name, f"{counts[name]:,}개")
            for name in ("공영", "민영", "단속 CCTV", "내 주차 기록", "내 위치")
            if name in counts
        ]
        with map_area:
            map_legend(legend_items, show_heat=bool(area_blobs))
            if area_blobs:
                hottest = max(b["count"] for b in area_blobs)
                st.caption(
                    f"단속 다발구역 {len(area_blobs):,}곳 · "
                    f"가장 뜨거운 곳은 누적 {hottest:,}건"
                )

# ── 결과: 카드 + 표 ───────────────────────────────────────────
# 표는 정보 밀도는 높지만 "어디로 갈지 고르는" 화면으로는 읽기 나쁘다.
# 상위 6곳은 카드로 크게 보여 주고, 나머지는 표로 접어 둔다.
if not no_results:
    section("추천 주차장", f"{sort_label or '추천순'} 기준 상위 {min(6, len(ranked))}곳")

    top = ranked.head(6)
    cards = []
    for _, lot in top.iterrows():
        available = lot.get("available")
        capacity = lot.get("capacity")
        cards.append(
            {
                "name": str(lot["parking_name"]),
                "category": str(lot.get("lot_category") or ""),
                "kind": str(lot.get("lot_type") or ""),
                "fee": int(lot["estimated_fee"]),
                "distance_km": float(lot["distance_km"]) if has_center else None,
                # 보행 속도 70m/분 기준 (신호 대기 포함한 대략치)
                "walk_min": max(1, round(float(lot["distance_km"]) * 1000 / 70))
                if has_center else None,
                "available": None if pd.isna(available) else int(available),
                "capacity": None if pd.isna(capacity) else int(capacity),
                "hours_text": str(lot.get("운영시간") or ""),
                # 원본에 요금이 안 실린 곳은 계산상 0원이 된다. 무료로 오해하지 않게 구분.
                "fee_known": bool(pd.notna(lot.get("base_fee"))),
            }
        )
    parking_cards(cards, hours)

    with st.container(horizontal=True, vertical_alignment="center"):
        st.markdown(f"**전체 {len(ranked):,}곳**", width="stretch")
        st.download_button(
            "CSV 내려받기",
            data=ranked.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"주차장_검색결과_{district}_{hours:g}시간.csv",
            mime="text/csv",
            icon=":material/download:",
            width="content",
        )

    # 카드로 훑고 고르는 게 기본이라, 자세히 비교하고 싶을 때만 표를 편다.
    display_columns = {
        "parking_name": st.column_config.TextColumn("주차장명", width="medium"),
        "lot_category": st.column_config.TextColumn("구분", width="small"),
        "lot_type": st.column_config.TextColumn("유형", width="small"),
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

    with st.expander("표로 자세히 비교하기", icon=":material/table_rows:"):
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

footer([
    "과거 단속 기록과 CCTV 위치를 기준으로 한 참고 정보입니다. "
    "현장 표지판과 노면 표시를 반드시 확인하세요.",
    "데이터: 서울시 주차정보안내시스템 · 종로구 단속 이력 · 단속 CCTV 위치정보",
])
    
