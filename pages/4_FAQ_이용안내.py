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
  # 현재 파일(4_FAQ_이용안내.py)의 위치를 기준으로 프로젝트 루트 경로를 찾아냄
  current_dir = os.path.dirname(os.path.abspath(__file__))
  # 루트 폴더 안의 data/cleaned/FAQ_sample_.csv 경로 조합
  file_path = os.path.join(current_dir, "..", "data", "cleaned", "FAQ_sample_.csv")

  df = pd.read_csv(file_path)
  return df


df = load_data()


# 💡 카테고리별 맞춤 아이콘(이모지) 매칭 함수
def get_category_icon(category_name):
  icon_map = {
      "견인": "🚗",
      "과태료 납부": "💳",
      "금지구역": "🚫",
      "다발구역": "📍",
      "단속기준": "📏",
      "단속완화": "🛡️",
      "서비스 이용": "⚙️",
      "의견 진술": "🗣️",
      "이의신청": "📝",
  }
  # 등록되지 않은 카테고리의 경우 기본 폴더 아이콘 반환
  return icon_map.get(category_name, "📁")


# 메인 타이틀 (아이콘 추가)
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

# 검색어 필터 적용 (질문 또는 답변에 검색어가 포함된 경우)
if search_query:
  filtered_df = filtered_df[
      filtered_df["question"].str.contains(search_query, case=False, na=False)
      | filtered_df["answer"].str.contains(search_query, case=False, na=False)
  ]

# --- 상단 메트릭 요약 (아이콘 적용) ---
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
  # 카테고리명을 누르면 열리는 아코디언 형태 구현
  for category, group in filtered_df.groupby("category"):
    # 카테고리별 맞춤 아이콘 가져오기
    icon = get_category_icon(category)

    # 카테고리 이름을 가진 아코디언 생성 (이모지 및 건수 포함)
    with st.expander(
        f"{icon}  **{category}**  —  총 {len(group)}개의 질문", expanded=True
    ):
      st.markdown("")

      # 해당 카테고리 안에 속한 QnA 목록 출력
      for _, row in group.iterrows():
        st.markdown(f"**Q. {row['question']}**")
        # 답변 영역을 인포박스로 감싸 가독성 및 글씨체 구분 극대화
        st.info(f"**A:** {row['answer']}")
        st.caption(
            f"📌 관련 기관/출처: {row['source_org']}  |  문서 ID: {row['faq_id']}"
        )
        st.markdown("")

      st.markdown("---")