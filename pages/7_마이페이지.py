"""
[담당: 승희] 마이페이지 — 주차 등록 + 주차 기록.

주차 등록은 두 가지 방식을 다 받는다.
    1) 주차장 선택  : 검색 페이지와 같은 목록에서 고르면 주소·좌표가 자동으로 채워진다
    2) 주소 직접 입력: 노상처럼 등록된 주차장이 아닌 곳

기록 로직은 common/parking_log.py, 로그인은 common/auth.py에 있고 여기는 화면만 담당한다.
"""

from datetime import datetime

import pandas as pd
import streamlit as st

import config
from common.auth import logout, require_login, storage_label
from common.kakao_map import build_map_html
from common.parking_data import load_parking_lots
from common.parking_log import add_log, delete_log, list_logs, summary
from common.ui import apply_style, hero

st.set_page_config(page_title="마이페이지", page_icon="🚙", layout="wide")
apply_style()
hero("🚙", "마이페이지", "주차한 위치를 기록하고 다시 찾아보세요. (담당: 승희)")

user = require_login("주차 기록은 로그인 후 이용할 수 있습니다.")

DIRECT_INPUT = "주소 직접 입력"

# ── 내 정보 ───────────────────────────────────────────────────
with st.container(horizontal=True, horizontal_alignment="left"):
    st.metric("아이디", user["username"])
    if st.button("로그아웃"):
        logout()
        st.rerun()

logs = list_logs(user["user_id"])
stats = summary(logs)

cols = st.columns(4)
cols[0].metric("총 주차 기록", f"{stats['total']:,}건")
cols[1].metric("이번 달", f"{stats['this_month']:,}건")
cols[2].metric("유료 비율", f"{stats['paid_ratio'] * 100:.0f}%")
cols[3].metric("가장 자주 간 곳", stats["favorite"])

st.write("")

# ── 주차 등록 ─────────────────────────────────────────────────
st.subheader("주차 등록", divider="gray")

lots, _ = load_parking_lots()
lot_names = sorted(lots["parking_name"].dropna().unique().tolist())

with st.form("parking_log_form"):
    place = st.selectbox(
        "주차장",
        [DIRECT_INPUT, *lot_names],
        help="검색 페이지의 주차장 목록에서 고르면 주소와 좌표가 자동으로 채워집니다.",
    )
    typed_address = st.text_input(
        "주소",
        placeholder="주차장을 직접 입력할 때만 채우세요 (예: 종로구 관철동 13-14)",
    )

    row = st.columns(3)
    parked_date = row[0].date_input("주차 날짜", value=datetime.now().date())
    parked_time = row[1].time_input("주차 시각", value=datetime.now().time())
    is_charged = row[2].toggle("유료 주차", value=True)

    memo = st.text_input("메모", placeholder="예: B2 3열, 기둥 옆")
    saved = st.form_submit_button("주차 기록 저장", type="primary")

if saved:
    parking_id = parking_name = None
    address = typed_address.strip()
    latitude = longitude = None

    if place != DIRECT_INPUT:
        match = lots[lots["parking_name"] == place]
        if not match.empty:
            lot = match.iloc[0]
            parking_id = str(lot["parking_id"])
            parking_name = str(lot["parking_name"])
            address = address or str(lot["address"])
            latitude = None if pd.isna(lot["latitude"]) else float(lot["latitude"])
            longitude = None if pd.isna(lot["longitude"]) else float(lot["longitude"])

    if not address:
        st.error("주차장을 고르거나 주소를 입력해주세요.")
    else:
        add_log(
            user_id=user["user_id"],
            address=address,
            parked_at=datetime.combine(parked_date, parked_time),
            is_charged=is_charged,
            parking_id=parking_id,
            parking_name=parking_name,
            latitude=latitude,
            longitude=longitude,
            memo=memo,
        )
        st.success(f"'{parking_name or address}' 주차 기록을 저장했습니다.")
        st.rerun()

# ── 주차 기록 ─────────────────────────────────────────────────
st.subheader("주차 기록", divider="gray")

if logs.empty:
    st.info("아직 주차 기록이 없습니다. 위에서 첫 기록을 남겨보세요.")
    st.stop()

latest = logs.iloc[0]
st.caption(
    f"가장 최근 주차: **{latest['place']}** · "
    f"{latest['parked_at']:%Y-%m-%d %H:%M}" + (f" · {latest['memo']}" if latest["memo"] else "")
)

mappable = logs.dropna(subset=["latitude", "longitude"])
if config.KAKAO_JS_KEY and not mappable.empty:
    map_df = pd.DataFrame(
        {
            "name": mappable["place"],
            "lat": mappable["latitude"],
            "lng": mappable["longitude"],
            "category": mappable["is_charged"].map({True: "유료", False: "무료"}),
            "info": mappable["parked_at"].dt.strftime("%Y-%m-%d %H:%M")
            + " · " + mappable["address"].fillna(""),
        }
    )
    st.iframe(
        build_map_html(
            map_df,
            app_key=config.KAKAO_JS_KEY,
            center_lat=mappable["latitude"].mean(),
            center_lng=mappable["longitude"].mean(),
            category_colors={"유료": "#ff9f1c", "무료": "#2ec4b6"},
            level=6,
            height=420,
        ),
        height=440,
    )

st.dataframe(
    logs[["parked_at", "place", "address", "is_charged", "memo"]],
    column_config={
        "parked_at": st.column_config.DatetimeColumn("주차 일시", format="YYYY-MM-DD HH:mm"),
        "place": st.column_config.TextColumn("주차장", width="medium"),
        "address": st.column_config.TextColumn("주소", width="medium"),
        "is_charged": st.column_config.CheckboxColumn("유료", width="small"),
        "memo": st.column_config.TextColumn("메모", width="medium"),
    },
    hide_index=True,
    height=320,
    key="my_logs",
)

# ── 기록 삭제 ─────────────────────────────────────────────────
with st.expander("기록 삭제"):
    options = {
        f"{r['parked_at']:%Y-%m-%d %H:%M} · {r['place']}": int(r["log_id"])
        for _, r in logs.iterrows()
    }
    target = st.selectbox("삭제할 기록", list(options), key="delete_target")
    if st.button("삭제", type="secondary"):
        delete_log(user["user_id"], options[target])
        st.success("삭제했습니다.")
        st.rerun()

st.caption(f"저장소: {storage_label()}")
