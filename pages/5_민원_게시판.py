import os
import pandas as pd
import streamlit as st

import config
from common.db import read_sql
from common.ui import apply_style, hero

# 1. 페이지 기본 설정 및 프로젝트 공통 스타일 적용
st.set_page_config(page_title="민원 게시판", page_icon="🙋‍♂️", layout="wide")
apply_style()

# 2. 상단 히어로 헤더 (타이틀: 민원 게시판 / 추천 서브 텍스트 반영)
hero("🙋‍♂️", "민원 게시판", "종로구 공개 상담민원 데이터를 한눈에 조회하고 검색해 보세요.")

# 테이블 레이아웃 및 스타일 커스텀 CSS
st.markdown("""
    <style>
    div[data-baseweb="input"] {
        border-radius: 6px !important;
    }
    .board-header {
        font-size: 16px !important;
        font-weight: 700 !important;
        color: #0F172A !important;
        padding: 8px 0 !important;
        text-align: left !important;
    }
    /* 제목 버튼 스타일 (파란색 박스/색상 제거 및 깔끔한 기본 텍스트 유지) */
    div[data-testid="stColumn"] button[kind="tertiary"] {
        text-align: left !important;
        justify-content: flex-start !important;
        padding: 0px !important;
        margin: 0px !important;
        font-size: 15px !important;
        font-weight: 500 !important;
        color: #0F172A !important;
        line-height: 1.4 !important;
        border: none !important;
        box-shadow: none !important;
        background-color: transparent !important;
    }
    div[data-testid="stColumn"] button[kind="tertiary"]:hover,
    div[data-testid="stColumn"] button[kind="tertiary"]:focus,
    div[data-testid="stColumn"] button[kind="tertiary"]:active {
        color: #0F172A !important;
        text-decoration: underline !important;
        background-color: transparent !important;
        border: none !important;
        box-shadow: none !important;
    }
    .row-divider {
        border: none;
        border-top: 1px solid #E2E8F0;
        margin: 6px 0 !important;
    }
    </style>
""", unsafe_allow_html=True)

# 3. 데이터 로딩 함수 (DB 및 data/cleaned CSV 로드)
COLUMNS = [
    "faq2_id", "q_title", "q_writer", "q_date",
    "question", "a_depart", "a_date", "answer",
]


@st.cache_data(ttl=600)
def load_faq_data() -> pd.DataFrame:
    """민원 목록. DB를 설정했으면 DB에서만 읽는다.

    - 민원 데이터가 들어있는 테이블은 FAQ 가 아니라 FAQ2 다.
      예전에는 FROM FAQ 로 되어 있어 쿼리가 매번 실패했고, 그 예외를
      조용히 삼키고 CSV를 읽어서 "DB를 쓰는 것처럼 보이지만 실은 CSV"인
      상태였다.
    - DB 설정이 있는데 실패하면 CSV로 숨기지 않고 그대로 알린다.
      CSV 폴백은 .env 가 없는 로컬 개발용으로만 남겨둔다.
    """
    if config.is_db_configured():
        return read_sql(f"SELECT {', '.join(COLUMNS)} FROM FAQ2")

    csv_path = os.path.join("data", "cleaned", "complain_faq2_result.csv")
    if os.path.exists(csv_path):
        return pd.read_csv(csv_path)

    return pd.DataFrame(columns=COLUMNS)


# 4. 메인 민원 게시판 화면
try:
    df = load_faq_data()
except Exception as exc:  # noqa: BLE001 - 접속/적재 문제를 화면에 그대로 알린다
    st.error(
        f"DB에서 민원 데이터를 읽지 못했습니다 ({type(exc).__name__}). "
        "테이블이 비었으면 `uv run python loaders/load_all.py --only FAQ2`, "
        "접속이 문제면 .env의 DB_* 값을 확인하세요.",
        icon=":material/database_off:",
    )
    st.stop()

if df.empty:
    st.warning(
        "⚠️ 민원 데이터가 없습니다. "
        "`uv run python loaders/load_all.py --only FAQ2` 로 적재해 주세요."
    )
else:
    # 검색창 및 건수 표시
    col_search, col_space, col_count = st.columns([4, 1, 2])
    with col_search:
        search_keyword = st.text_input("검색", value="", placeholder="🔍 제목 또는 질문 내용을 검색해보세요...", label_visibility="collapsed")
    with col_count:
        st.markdown(f"<div style='text-align: right; padding-top: 8px; font-size: 15px; color: #475569;'>총 <b>{len(df)}</b>건의 민원</div>", unsafe_allow_html=True)

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
        st.info("검색 결과가 없습니다.")
    else:
        h_col1, h_col2, h_col3, h_col4 = st.columns([1, 7, 2, 2.5])
        h_col1.markdown("<div class='board-header'>번호</div>", unsafe_allow_html=True)
        h_col2.markdown("<div class='board-header'>제목</div>", unsafe_allow_html=True)
        h_col3.markdown("<div class='board-header'>작성자</div>", unsafe_allow_html=True)
        h_col4.markdown("<div class='board-header'>작성일</div>", unsafe_allow_html=True)

        st.markdown("<hr style='border:none; border-top:2px solid #0F172A; margin:0 0 8px 0;' />", unsafe_allow_html=True)

        for i, row in page_df.iterrows():
            r_col1, r_col2, r_col3, r_col4 = st.columns([1, 7, 2, 2.5])
            
            display_num = row['faq2_id'] if 'faq2_id' in row and pd.notna(row['faq2_id']) else (i + 1)
            r_col1.markdown(f"<div style='color: #475569; font-size: 15px; padding-top: 2px;'>{int(display_num)}</div>", unsafe_allow_html=True)
            
            if r_col2.button(row['q_title'], key=f"title_{i}_{row['q_date']}", type="tertiary"):
                show_detail_dialog(row)
            
            writer = str(row['q_writer']) if pd.notna(row['q_writer']) else "-"
            r_col3.markdown(f"<div style='color: #475569; font-size: 15px; padding-top: 2px;'>{writer}</div>", unsafe_allow_html=True)
            
            r_col4.markdown(f"<div style='color: #64748B; font-size: 14px; text-align: left; padding-top: 2px;'>{row['q_date']}</div>", unsafe_allow_html=True)

            st.markdown("<hr class='row-divider' />", unsafe_allow_html=True)

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