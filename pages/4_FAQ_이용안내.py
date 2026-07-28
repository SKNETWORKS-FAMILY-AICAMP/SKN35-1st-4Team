import os
import unicodedata
import base64
import re
import pandas as pd
import streamlit as st

# 페이지 기본 설정
st.set_page_config(
    page_title="FAQ 대시보드", page_icon="💡", layout="wide"
)

# --- [UI/UX 디자인 개선] 미선택 탭에 은은한 배경색과 테두리 적용 ---
st.markdown(
    """
    <style>
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    
    /* 전체 카테고리 탭 영역 컨테이너: 균일한 간격(flex) 및 하단 직선 배치 */
    .custom-tab-container {
        display: flex;
        gap: 8px;
        background-color: transparent;
        padding: 4px 0px 12px 0px;
        border-bottom: 2px solid #e2e8f0;
        width: 100%;
        box-sizing: border-box;
        align-items: center;
        margin-bottom: 25px;
    }
    
    /* Streamlit 컬럼 너비를 무시하고 모든 버튼이 동일한 너비를 갖도록 설정 */
    div[data-testid="stHorizontalBlock"] > div {
        flex: 1 1 0% !important;
        max-width: none !important;
    }

    /* 카테고리 버튼 기본 스타일 (미선택 탭에 은은한 배경색과 연한 테두리 적용) */
    div[data-testid="stHorizontalBlock"] > div button,
    div[data-testid="stHorizontalBlock"] > div button * {
        font-size: 1.1rem !important;
        font-weight: 700 !important;
        color: #475569 !important;
        -webkit-font-smoothing: antialiased;
    }

    div[data-testid="stHorizontalBlock"] > div button {
        width: 100% !important;
        background-color: #fafaf9 !important;
        border: 1px solid #e7e5e4 !important;
        border-radius: 8px !important;
        padding: 10px 4px !important;
        text-align: center;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        transition: all 0.2s ease-in-out;
    }
    
    /* 미선택 탭 마우스 올렸을 때(Hover) 효과 */
    div[data-testid="stHorizontalBlock"] > div button:hover {
        background-color: #fff7ed !important;
        border-color: #fdba74 !important;
        color: #c2410c !important;
    }

    /* 💡 활성화된 카테고리 버튼 스타일 (오렌지 포인트) */
    div[data-testid="stHorizontalBlock"] > div button[kind="secondary"] {
        background-color: #fff7ed !important;
        border: 2px solid #f97316 !important;
        color: #c2410c !important;
    }

    /* 💡 열린(Expanded) 아코디언의 '상단 질문 영역(summary)' 배경을 따뜻한 오렌지 베이지빛(#fff7ed)으로 강조 */
    details[open] > summary {
        background-color: #fff7ed !important;
        border-radius: 8px 8px 0 0 !important;
        border-bottom: 1px solid #fed7aa !important;
    }

    /* 열린 아코디언 전체 박스의 테두리를 오렌지 포인트 색상으로 강조 */
    details[open] {
        border: 2px solid #f97316 !important;
        border-radius: 8px !important;
        background-color: #ffffff !important;
        box-shadow: 0 4px 6px -1px rgba(249, 115, 22, 0.1);
    }

    /* 닫혀있는 아코디언 기본 박스 스타일 */
    details {
        border: 2px solid #e2e8f0 !important;
        border-radius: 8px !important;
        transition: all 0.2s ease-in-out;
    }

    /* 아코디언 질문(Q) 글자 크기와 굵기 강조 */
    details summary p {
        font-weight: 700 !important;
        font-size: 1.15rem !important;
        color: #1e293b !important;
    }
    
    /* 아코디언 호버 시 배경 강조 효과 (열려있지 않을 때만) */
    details:not([open]):hover {
        background-color: #f8fafc;
        border-color: #cbd5e1 !important;
        border-radius: 8px;
    }
    </style>
""",
    unsafe_allow_html=True,
)


# 데이터 로드 함수 (절대 경로 적용)
@st.cache_data
def load_data():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(current_dir, "..", "data", "cleaned", "FAQ_sample_.csv")
    df = pd.read_csv(file_path)
    return df


df = load_data()


# 안전한 이미지 경로 탐색 함수
def get_category_image_path(category_name):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(current_dir)
    
    possible_dirs = [
        os.path.join(root_dir, "assets", "jpg"),
        os.path.join(root_dir, "assets"),
        os.path.join(current_dir, "..", "assets", "jpg"),
        os.path.join(current_dir, "..", "assets"),
        os.path.join(current_dir, "assets", "jpg"),
        os.path.join(current_dir, "assets"),
    ]
    
    target_name = unicodedata.normalize('NFC', category_name)

    for assets_dir in possible_dirs:
        if os.path.exists(assets_dir) and os.path.isdir(assets_dir):
            for f in os.listdir(assets_dir):
                name_part, ext = os.path.splitext(f)
                if unicodedata.normalize('NFC', name_part) == target_name:
                    return os.path.join(assets_dir, f)
                    
    return None


# Base64 변환 함수
def get_image_as_base64(path):
    if path and os.path.exists(path):
        with open(path, "rb") as f:
            data = f.read()
        encoded = base64.b64encode(data).decode()
        ext = path.split(".")[-1].lower()
        mime = "image/jpeg" if ext in ["jpg", "jpeg"] else "image/png"
        return f"data:{mime};base64,{encoded}"
    return None


# 답변 가독성 개선 처리 함수
def format_answer_smart(text):
    if not isinstance(text, str):
        return str(text)
    
    sentences = re.split(r'(?<=[.?!])\s+', text.strip())
    
    formatted_lines = []
    for sentence in sentences:
        sentence = sentence.strip()
        if sentence:
            formatted_lines.append(sentence)
            
    return "<br><br>".join(formatted_lines)


# 메인 타이틀
st.title("💡 자주 묻는 질문(FAQ) 센터")
st.markdown(
    "궁금한 사항을 카테고리별로 확인하거나 통합 검색을 통해 빠르게 찾아보세요."
)

# 사이드바 필터 구성
st.sidebar.header("🔍 검색 및 필터")
st.sidebar.markdown("원하시는 정보를 빠르게 찾아보세요.")

# 검색어 입력
search_query = st.sidebar.text_input("질문/답변 검색", "", placeholder="키워드를 입력하세요")

# 데이터 필터링 로직
filtered_df = df.copy()

# 검색어 필터 적용
if search_query:
    filtered_df = filtered_df[
        filtered_df["question"].str.contains(search_query, case=False, na=False)
        | filtered_df["answer"].str.contains(search_query, case=False, na=False)
    ]

# 상단 통계 항목
st.markdown(
    f"""
    <div style="display: flex; gap: 20px; font-size: 0.9rem; color: #64748b; margin-bottom: 15px;">
        <div>📊 전체 FAQ: <b>{len(df)}개</b></div>
        <div>🔍  검색 결과: <b>{len(filtered_df)}개</b></div>
        <div>🏷️ 카테고리 수: <b>{df['category'].nunique()}개</b></div>
    </div>
    """,
    unsafe_allow_html=True,
)

# 메인 콘텐츠 영역
if filtered_df.empty:
    st.warning("🔍 검색 결과가 없습니다. 다른 검색어나 키워드를 입력해 보세요.")
else:
    requested_order = [
        "단속기준",
        "단속완화",
        "다발구역",
        "견인",
        "과태료 납부",
        "이의신청",
        "의견 진술",
        "서비스 이용",
        "금지구역",
    ]
    
    available_categories = [cat for cat in requested_order if cat in filtered_df["category"].unique()]
    
    for cat in filtered_df["category"].unique():
        if cat not in available_categories:
            available_categories.append(cat)

    if not available_categories:
        st.warning("🔍 해당하는 카테고리 데이터가 없습니다.")
    else:
        if "selected_faq_category" not in st.session_state or st.session_state["selected_faq_category"] not in available_categories:
            st.session_state["selected_faq_category"] = available_categories[0]

        st.markdown('<div class="custom-tab-container">', unsafe_allow_html=True)
        cols = st.columns(len(available_categories))
        
        for idx, cat in enumerate(available_categories):
            with cols[idx]:
                is_active = (cat == st.session_state["selected_faq_category"])
                
                # 💡 선택된 탭: 파일철 모양 + 사이트 테마 컬러(오렌지 포인트) 적용
                if is_active:
                    st.markdown(
                        f"""
                        <style>
                        div[data-testid="stHorizontalBlock"] > div:nth-child({idx+1}) button,
                        div[data-testid="stHorizontalBlock"] > div:nth-child({idx+1}) button * {{
                            font-size: 1.1rem !important;
                            font-weight: 700 !important;
                            color: #c2410c !important;
                        }}
                        div[data-testid="stHorizontalBlock"] > div:nth-child({idx+1}) button {{
                            background-color: #fff7ed !important;
                            border: 2px solid #f97316 !important;
                            border-radius: 8px !important;
                            clip-path: polygon(0 25%, 32% 25%, 50% 0, 100% 0, 100% 100%, 0 100%);
                            padding: 10px 4px !important;
                        }}
                        </style>
                        """,
                        unsafe_allow_html=True,
                    )
                
                if st.button(cat, key=f"tab_btn_{idx}", use_container_width=True):
                    st.session_state["selected_faq_category"] = cat
                    st.rerun()
                    
        st.markdown('</div>', unsafe_allow_html=True)

        current_category = st.session_state["selected_faq_category"]
        group = filtered_df[filtered_df["category"] == current_category]
        
        img_path = get_category_image_path(current_category)
        base64_img = get_image_as_base64(img_path)
        
        if base64_img:
            icon_html = f'<img src="{base64_img}" style="width: 64px; height: 64px; vertical-align: middle; margin-right: 18px; object-fit: contain;">'
        else:
            icon_html = '<span style="font-size: 2.6rem; margin-right: 14px; vertical-align: middle;">📁</span>'

        st.markdown(
            f"""
            <div style="display: flex; align-items: center; padding-top: 10px; padding-bottom: 10px; margin-top: 10px; margin-bottom: 8px;">
                {icon_html}
                <span style="font-size: 2.5rem; font-weight: 800; color: #1e293b; line-height: 1.1; letter-spacing: -0.5px;">{current_category}</span>
                <span style="font-size: 1.2rem; color: #64748b; margin-left: 16px; font-weight: 600;">({len(group)}개의 질문)</span>
            </div>
            <hr style="border: none; border-top: 2px solid #cbd5e1; margin-top: 8px; margin-bottom: 20px;">
            """,
            unsafe_allow_html=True,
        )

        for _, row in group.iterrows():
            with st.expander(f"Q. {row['question']}"):
                formatted_ans = format_answer_smart(row['answer'])
                st.markdown(
                    f"""
                    <div style="margin-top: 4px; margin-bottom: 12px;">
                        <div style="font-size: 1.2rem; font-weight: 600; line-height: 1.7; color: #1e293b;">
                            {formatted_ans}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                st.markdown("---")
                st.caption(
                    f"📌 관련 기관/출처: {row['source_org']}  |  문서 ID: {row['faq_id']}"
                )