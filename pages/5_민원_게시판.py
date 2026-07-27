import os
import pandas as pd
import streamlit as st

# 1. 페이지 기본 설정
st.set_page_config(page_title="민원 게시판", layout="wide")

# 리얼 게시판 스타일 CSS
st.markdown("""
    <style>
    div[data-baseweb="input"] {
        border-radius: 6px !important;
    }

    .board-header {
        font-size: 17px !important;
        font-weight: 700 !important;
        color: #0F172A !important;
        padding: 8px 0 !important;
        text-align: left !important;
    }
    
    div[data-testid="stColumn"] button[kind="tertiary"] {
        text-align: left !important;
        justify-content: flex-start !important;
        padding: 0px !important;
        margin: 0px !important;
        font-size: 15px !important;
        font-weight: 500 !important;
        color: #0F172A !important;
        line-height: 1.4 !important;
    }
    div[data-testid="stColumn"] button[kind="tertiary"]:hover {
        color: #2563EB !important;
        text-decoration: underline !important;
        background-color: transparent !important;
    }
    
    .row-divider {
        border: none;
        border-top: 1px solid #E2E8F0;
        margin: 6px 0 !important;
    }
    </style>
""", unsafe_allow_html=True)

st.title("민원 게시판")
st.caption("종로구 공개 상담민원 수집 데이터입니다.")

# 2. 데이터 불러오기
csv_path = "minwon_faq2_result.csv"

if not os.path.exists(csv_path):
    st.error("`minwon_faq2_result.csv` 파일을 찾을 수 없습니다. 크롤러를 먼저 실행해 주세요.")
else:
    df = pd.read_csv(csv_path)

    st.markdown("---")

    # 검색 및 전체 개수 표시
    col_search, col_space, col_count = st.columns([4, 1, 2])
    
    with col_search:
        search_keyword = st.text_input("검색", value="", placeholder="🔍 제목 또는 질문 내용을 검색해보세요...", label_visibility="collapsed")
    
    with col_count:
        st.markdown(f"<div style='text-align: right; padding-top: 8px; font-size: 15px; color: #475569;'>총 <b>{len(df)}</b>건의 민원</div>", unsafe_allow_html=True)

    # 검색 필터링
    if search_keyword:
        filtered_df = df[
            df['q_title'].astype(str).str.contains(search_keyword, case=False, na=False) |
            df['question'].astype(str).str.contains(search_keyword, case=False, na=False)
        ].reset_index(drop=True)
    else:
        filtered_df = df.reset_index(drop=True)

    # 3. 페이지네이션 (10개씩)
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

    # 4. 상세 모달 Dialog (원문 링크 완전히 제거됨)
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

    # 5. 게시판 목록 출력
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

        # 6. 하단 페이지네이션 UI
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