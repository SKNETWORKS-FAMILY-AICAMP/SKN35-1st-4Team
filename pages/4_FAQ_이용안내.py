import os
import pandas as pd
import streamlit as st

# 페이지 기본 설정
st.set_page_config(
    page_title="FAQ 대시보드", page_icon="💡", layout="wide"
)

# --- [UI/UX 디자인 개선] 커스텀 CSS 적용 ---
st.markdown(
    """
    <style>
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    
    /* 상단 통계(Metric) 카드 스타일링 */
    div[data-testid="stMetric"] {
        background-color: #f8f9fa;
        border: 1px solid #e9ecef;
        padding: 15px 20px;
        border-radius: 12px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.02);
    }
    
    /* 아코디언 타이틀 폰트 강조 */
    details summary p {
        font-weight: 600;
        font-size: 1.05rem;
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


# 💡 [스마트 상향식 경로 탐색] assets 폴더를 자동으로 찾아내는 함수
def get_category_image_path(category_name):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 현재 디렉토리부터 시작해서 부모 디렉토리로 올라가며 assets 폴더를 탐색
    assets_dir = None
    target_dir = current_dir
    for _ in range(3):
        candidate = os.path.join(target_dir, "assets")
        if os.path.exists(candidate) and os.path.isdir(candidate):
            assets_dir = candidate
            break
        target_dir = os.path.dirname(target_dir)
        
    # 만약 찾지 못했다면 기본 상대 경로 지정
    if not assets_dir:
        assets_dir = os.path.join(current_dir, "..", "assets")

    # 스크린샷 내 실제 파일명과 100% 매칭
    image_map = {
        "견인": "towing_area.png",
        "과태료 납부": "payment.png",
        "금지구역": "no_parking_zone_.png",
        "다발구역": "frequent_illegal_parking_area.png",
        "단속기준": "enforcement_standards.png",
        "단속완화": "easing_enforcement.jpg",
        "서비스 이용": "service.png",
        "의견 진술": "opinion_statement.png",
        "이의신청": "objection.png",
    }
    
    filename = image_map.get(category_name, "service.png")
    return os.path.join(assets_dir, filename)


# 메인 타이틀
st.title("💡 자주 묻는 질문(FAQ) 센터")
st.markdown(
    "궁금한 사항을 카테고리별로 확인하거나 통합 검색을 통해 빠르게 찾아보세요."
)

# --- 사이드바 필터 구성 ---
st.sidebar.header("🔍 검색 및 필터")
st.sidebar.markdown("원하시는 정보를 빠르게 찾아보세요.")

# 검색어 입력
search_query = st.sidebar.text_input("질문/답변 검색", "", placeholder="키워드를 입력하세요")

# 카테고리 선택 필터
categories = ["전체"] + list(df["category"].unique())
selected_category = st.sidebar.selectbox("카테고리 선택", categories)

# --- 데이터 필터링 로직 ---
filtered_df = df.copy()

# 카테고리 필터 적용
if selected_category != "전체":
    filtered_df = filtered_df[filtered_df["category"] == selected_category]

# 검색어 필터 적용
if search_query:
    filtered_df = filtered_df[
        filtered_df["question"].str.contains(search_query, case=False, na=False)
        | filtered_df["answer"].str.contains(search_query, case=False, na=False)
    ]

# --- 상단 메트릭 요약 ---
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("📊 전체 FAQ 항목", f"{len(df)}개")
with col2:
    st.metric("🎯 선택된 카테고리 항목", f"{len(filtered_df)}개")
with col3:
    st.metric("🏷️ 등록된 카테고리 수", f"{df['category'].nunique()}개")

st.markdown("---")

# --- 메인 콘텐츠 영역 ---
if filtered_df.empty:
    st.warning("🔍 검색 결과가 없습니다. 다른 검색어나 카테고리를 입력해 보세요.")
else:
    # 카테고리별 그룹화
    for category, group in filtered_df.groupby("category"):
        img_path = get_category_image_path(category)

        # 아코디언 생성
        with st.expander(
            f"📁  **{category}**  —  총 {len(group)}개의 질문", expanded=True
        ):
            st.markdown("")

            # 🖼️ 이미지 아이콘과 카테고리 타이틀을 나란히 배치
            col_img, col_title = st.columns([0.05, 0.95])
            with col_img:
                if os.path.exists(img_path):
                    st.image(img_path, width=35)
                else:
                    st.error(f"❌ 이미지 없음\n위치: {img_path}")
            with col_title:
                st.markdown(f"### {category}")

            st.markdown("---")

            # 해당 카테고리 안에 속한 QnA 목록 출력
            for _, row in group.iterrows():
                st.markdown(f"**Q. {row['question']}**")
                st.info(f"**A:** {row['answer']}")
                st.caption(
                    f"📌 관련 기관/출처: {row['source_org']}  |  문서 ID: {row['faq_id']}"
                )
                st.markdown("")

        st.markdown("---")