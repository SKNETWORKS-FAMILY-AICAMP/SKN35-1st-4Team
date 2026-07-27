import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path :
    sys.path.append(BASE_DIR)

import pandas as pd
import streamlit as st

import config
from common.db import read_sql
from common.ui import MARK_BOARD, empty_state, hero

# 1. 페이지 기본 설정 및 프로젝트 공통 스타일 적용

# 2. 상단 히어로 헤더 (타이틀: 민원 게시판 / 추천 서브 텍스트 반영)
HERO_SLOT = st.container()

# 테이블 레이아웃 및 스타일 커스텀 CSS
st.html("""
    <style>
    /* 게시판 표 — 앗차차 팔레트에 맞춘 카드형 행 */
    .board-header {
        font-size: 14px !important;
        font-weight: 700 !important;
        color: #6B625C !important;
        padding: 6px 0 !important;
        letter-spacing: .02em;
    }
    div[data-testid="stColumn"] button[kind="tertiary"] {
        text-align: left !important;
        justify-content: flex-start !important;
        padding: 0 !important;
        margin: 0 !important;
        font-size: 15px !important;
        font-weight: 600 !important;
        color: #26201D !important;
        line-height: 1.45 !important;
        border: none !important;
        box-shadow: none !important;
        background-color: transparent !important;
        transition: color .15s ease;
    }
    div[data-testid="stColumn"] button[kind="tertiary"]:hover,
    div[data-testid="stColumn"] button[kind="tertiary"]:focus,
    div[data-testid="stColumn"] button[kind="tertiary"]:active {
        color: #D14314 !important;
        text-decoration: underline !important;
        text-underline-offset: 3px;
        background-color: transparent !important;
        border: none !important;
        box-shadow: none !important;
        transform: none !important;
    }
    .row-divider {
        border: none;
        border-top: 1px solid #F2E6DD;
        margin: 8px 0 !important;
    }
    .board-num {
        display: inline-flex; align-items: center; justify-content: center;
        min-width: 30px; height: 24px; padding: 0 8px;
        border-radius: 999px;
        background: #FFF1E8; color: #B8380F;
        font-size: 13px; font-weight: 700;
    }
    .board-meta { color: #6B625C; font-size: 14px; padding-top: 3px; }
    </style>
""")

# 3. 데이터 로딩 함수 (TiDB Cloud 데이터베이스에서 직접 연동)
#
# 민원 데이터가 들어있는 테이블은 FAQ 가 아니라 complain 이다(예전 이름 FAQ2).
# CSV 폴백은 두지 않는다 — 예전에는 쿼리가 실패해도 조용히 CSV를 읽어서
# "DB를 쓰는 것처럼 보이지만 실은 CSV"인 상태를 눈치챌 수 없었다.
COLUMNS = [
    "faq2_id", "q_title", "q_writer", "q_date",
    "question", "a_depart", "a_date", "answer",
]


@st.cache_data(ttl=600)
def load_faq_data() -> pd.DataFrame:
    # 화면의 번호는 원본 faq2_id 가 아니라 작성일 오름차순 일련번호로 매긴다
    query = """
        SELECT
            ROW_NUMBER() OVER (ORDER BY q_date ASC, faq2_id ASC) AS faq2_id,
            q_title,
            q_writer,
            q_date,
            question,
            a_depart,
            a_date,
            answer
        FROM complain
        ORDER BY q_date DESC
    """
    return read_sql(query)


# 4. 메인 민원 게시판 화면
try:
    df = load_faq_data()
except Exception as exc:  # noqa: BLE001 - 접속/적재 문제를 화면에 그대로 알린다
    st.error(
        f"❌ TiDB Cloud 데이터베이스 연동 오류 ({type(exc).__name__}): {exc}\n\n"
        "테이블이 비었으면 `uv run python loaders/load_all.py --only complain`, "
        "접속이 문제면 .env의 DB_* 값을 확인하세요.",
        icon=":material/database_off:",
    )
    st.stop()

with HERO_SLOT:
    hero(
        MARK_BOARD,
        "이런 민원이 올라왔어요",
        "종로구에 실제로 접수된 주정차 관련 민원과 담당 부서의 답변입니다.",
        chips=[f"민원 <b>{len(df):,}</b>건"] if not df.empty else None,
    )

if df.empty:
    empty_state(
        "chat",
        "아직 민원 데이터가 없어요",
        "터미널에서 loaders/load_all.py --only complain 을 실행해 적재해 주세요.",
    )
else:
    # 검색창 및 건수 표시
    col_search, col_space, col_count = st.columns([4, 1, 2])
    with col_search:
        search_keyword = st.text_input("검색", value="", placeholder="🔍 제목 또는 질문 내용을 검색해보세요...", label_visibility="collapsed")
    with col_count:
        st.html(f"<div style='text-align:right; padding-top:8px; font-size:15px; color:#6B625C;'>총 <b>{len(df)}</b>건의 민원</div>")

    # 검색어 필터링
    if search_keyword:
        filtered_df = df[
            df['q_title'].astype(str).str.contains(search_keyword, case=False, na=False) |
            df['question'].astype(str).str.contains(search_keyword, case=False, na=False)
        ].reset_index(drop=True)
    else:
        filtered_df = df.reset_index(drop=True)

    # 페이지네이션 (10개씩)
    ITEMS_PER_PAGE = 10
    total_items = len(filtered_df)
    total_pages = max(1, (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)

    if "current_page" not in st.session_state:
        st.session_state.current_page = 1

    if "last_search" not in st.session_state or st.session_state.last_search != search_keyword:
        st.session_state.current_page = 1
        st.session_state.last_search = search_keyword

    if st.session_state.current_page > total_pages:
        st.session_state.current_page = total_pages

    start_idx = (st.session_state.current_page - 1) * ITEMS_PER_PAGE
    end_idx = min(start_idx + ITEMS_PER_PAGE, total_items)
    page_df = filtered_df.iloc[start_idx:end_idx]

    # 상세 보기 Dialog
    @st.dialog("민원 상세 보기", width="large")
    def show_detail_dialog(row):
        col_t, col_d = st.columns([3, 1])
        with col_t:
            st.subheader(row['q_title'])
        with col_d:
            st.caption(f"작성일: {row['q_date']}")

        st.markdown(f"**작성자**: {row['q_writer']}")
        st.divider()

        st.markdown("### 질문 내용")
        st.info(row['question'] if pd.notna(row['question']) and row['question'] != "" else "질문 본문 내용이 없습니다.")

        st.divider()

        st.markdown("### 답변 내용")
        st.markdown(f"**담당부서**: {row['a_depart']} | **답변일자**: {row['a_date']}")
        st.success(row['answer'] if pd.notna(row['answer']) and row['answer'] != "" else "답변 내용이 없습니다.")

    # 테이블 헤더 및 목록 출력
    if total_items == 0:
        empty_state("chat", "검색 결과가 없어요", "다른 낱말로 검색해 보세요.")
    else:
        h_col1, h_col2, h_col3, h_col4 = st.columns([1, 7, 2, 2.5])
        h_col1.markdown("<div class='board-header'>번호</div>", unsafe_allow_html=True)
        h_col2.markdown("<div class='board-header'>제목</div>", unsafe_allow_html=True)
        h_col3.markdown("<div class='board-header'>작성자</div>", unsafe_allow_html=True)
        h_col4.markdown("<div class='board-header'>작성일</div>", unsafe_allow_html=True)

        st.html("<hr style='border:none; border-top:2px solid #D14314; margin:0 0 10px 0;' />")

        for i, row in page_df.iterrows():
            r_col1, r_col2, r_col3, r_col4 = st.columns([1, 7, 2, 2.5])
            
            display_num = row['faq2_id'] if 'faq2_id' in row and pd.notna(row['faq2_id']) else (i + 1)
            r_col1.html(f"<span class='board-num'>{int(display_num)}</span>")
            
            if r_col2.button(row['q_title'], key=f"title_{i}_{row['q_date']}", type="tertiary"):
                show_detail_dialog(row)
            
            writer = str(row['q_writer']) if pd.notna(row['q_writer']) else "-"
            r_col3.html(f"<div class='board-meta'>{writer}</div>")
            
            r_col4.html(f"<div class='board-meta'>{row['q_date']}</div>")

            st.html("<hr class='row-divider' />")

        # 페이지네이션 UI
        st.write("")
        p_col1, p_col2, p_col3, p_col4, p_col5 = st.columns([1, 1, 2, 1, 1])

        with p_col1:
            if st.button("≪ 처음", disabled=(st.session_state.current_page == 1), use_container_width=True):
                st.session_state.current_page = 1
                st.rerun()

        with p_col2:
            if st.button("◀ 이전", disabled=(st.session_state.current_page == 1), use_container_width=True):
                st.session_state.current_page -= 1
                st.rerun()

        with p_col3:
            st.markdown(
                f"<div style='text-align: center; font-weight: 600; margin-top: 6px; color: #334155;'>"
                f"{st.session_state.current_page} / {total_pages} 페이지"
                f"</div>",
                unsafe_allow_html=True
            )

        with p_col4:
            if st.button("다음 ▶", disabled=(st.session_state.current_page >= total_pages), use_container_width=True):
                st.session_state.current_page += 1
                st.rerun()

        with p_col5:
            if st.button("끝 ≫", disabled=(st.session_state.current_page >= total_pages), use_container_width=True):
                st.session_state.current_page = total_pages
                st.rerun()