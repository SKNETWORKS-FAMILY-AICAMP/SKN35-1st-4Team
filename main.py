"""
프로젝트 진입점 (홈 화면).

실행
    uv run streamlit run main.py

왼쪽 사이드바에 pages/ 폴더의 페이지들이 자동으로 나열된다.
지금은 팀원별로 각자 페이지에서 작업하고, 이후 통합할 예정
(FAQ A/B는 최종적으로 한 페이지로 합칠 계획).
"""

import streamlit as st

import config
from common.ui import apply_style, feature_card, hero, status_chip

st.set_page_config(page_title="주정차 정보 조회 시스템", page_icon="🚗", layout="wide")
apply_style()

hero(
    "🚗",
    "주정차 제한 정보 & 주변 주차장 안내",
    "공공데이터와 웹 크롤링으로 만드는 우리 동네 주정차 도우미 — 왼쪽 사이드바에서 기능을 선택하세요.",
)

# ── 기능 소개 카드 (팀원별 담당 페이지) ─────────────────────────
row1 = st.columns(3)
with row1[0]:
    st.markdown(
        feature_card(
            "🔥", "단속 다발구역",
            "서울시 불법주정차 단속이력을 분석해 단속이 잦은 구역 TOP N과 월별 추이를 보여줍니다.",
            "치훈",
        ),
        unsafe_allow_html=True,
    )
with row1[1]:
    st.markdown(
        feature_card(
            "📷", "CCTV 지도",
            "불법주정차/전용차로 위반 단속 CCTV 위치를 카카오맵 위에 마커로 표시합니다.",
            "종원",
        ),
        unsafe_allow_html=True,
    )
with row1[2]:
    st.markdown(
        feature_card(
            "🅿️", "주차장 검색",
            "공영주차장(공공데이터)과 민영주차장(크롤링)을 통합 검색하고 지도로 확인합니다.",
            "승희",
        ),
        unsafe_allow_html=True,
    )

st.write("")

row2 = st.columns(3)
with row2[0]:
    st.markdown(
        feature_card(
            "💬", "FAQ - 이용안내",
            "공영주차장 이용·정기권·요금감면 등 자주 묻는 질문 (서울시설공단 크롤링).",
            "연주 또는 은미",
        ),
        unsafe_allow_html=True,
    )
with row2[1]:
    st.markdown(
        feature_card(
            "🚛", "FAQ - 단속·견인·이의신청",
            "단속기준, 견인 절차, 이의신청 방법 안내와 과태료 계산기 (크롤링 + 고시공고).",
            "연주 또는 은미",
        ),
        unsafe_allow_html=True,
    )
with row2[2]:
    st.markdown(
        feature_card(
            "🔀", "통합 예정",
            "지금은 각자 페이지에서 개발하고, 완성되면 FAQ 두 페이지를 하나로 합치고 전체 메뉴를 정리할 예정입니다.",
            "팀 공동",
        ),
        unsafe_allow_html=True,
    )

st.write("")

# ── 환경 설정 상태 ──────────────────────────────────────────────
st.subheader("환경 설정 상태")
chips = "".join(
    [
        status_chip("MySQL 연결정보", config.is_db_configured()),
        status_chip("카카오 JavaScript 키", bool(config.KAKAO_JS_KEY)),
        status_chip("공공데이터포털 키", bool(config.DATA_GO_KR_API_KEY)),
    ]
)
st.markdown(chips, unsafe_allow_html=True)

if not config.is_db_configured():
    st.info(
        "MySQL 접속 정보가 아직 없어도 모든 페이지는 **샘플 데이터**로 동작합니다. "
        "`.env.example`을 복사해 `.env`를 만들고 DBeaver에서 만든 DB 정보를 채우면 "
        "실제 데이터로 전환됩니다."
    )
if not config.KAKAO_JS_KEY:
    st.warning("`.env`에 KAKAO_JS_KEY가 없으면 지도 관련 페이지가 동작하지 않습니다.")