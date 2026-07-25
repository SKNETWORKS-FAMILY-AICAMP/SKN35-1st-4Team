"""
[담당: 은미] FAQ - 공영주차장 이용안내 페이지 (크롤링 A).

데이터 소스: 서울시설공단 공영주차장 FAQ (sisul.or.kr, 정적 게시판)
    -> collectors/faq_crawler_a.py 로 수집, FAQ 테이블에 적재
    -> category: 이용안내 / 결제오류 / 정기권 / 요금감면

⚠ 통합 계획: 이 페이지와 "FAQ - 단속·견인·이의신청"(연주)은 같은 FAQ 테이블을
쓰기 때문에, 나중에 category 필터만 합치면 한 페이지로 통합할 수 있다.
"""

import pandas as pd
import streamlit as st

import config
from common.db import read_sql
from common.ui import apply_style, hero

st.set_page_config(page_title="FAQ - 이용안내", page_icon="💬", layout="wide")
apply_style()
hero("💬", "FAQ - 공영주차장 이용안내", "정기권, 요금감면, 결제 문제 등 이용 관련 궁금증을 검색하세요. (담당: 은미)")

# 이 페이지가 담당하는 카테고리 (크롤링 A 수집분)
MY_CATEGORIES = ["이용안내", "결제오류", "정기권", "요금감면"]

SAMPLE_FAQ = pd.DataFrame(
    [
        {
            "category": "정기권",
            "question": "정기권 이용자인데 14일마다 출차를 해야 하는 이유가 궁금합니다.",
            "answer": "공영주차장 차고지화 방지를 위해 장기 주차(14일 이상) 차량을 대상으로 출차를 유도하고 있습니다.",
            "source": "서울시설공단 공영주차장 FAQ (sisul.or.kr)",
        },
        {
            "category": "요금감면",
            "question": "주차요금을 감면받을 수 있는 대상은 누구인가요?",
            "answer": "장애인·국가유공상이자 등 80%, 경차/저공해 50%, 다둥이행복카드(2자녀 이상) 50% 등 조례 기준으로 감면됩니다.",
            "source": "서울시설공단 공영주차장 FAQ (sisul.or.kr)",
        },
        {
            "category": "결제오류",
            "question": "정기권을 취소하고 환불받을 수 있나요?",
            "answer": "이용개시 전이라면 결제수단별 기한 내 직접 취소 가능하며, 기한이 지나면 홈페이지에서 환불신청서를 접수해야 합니다.",
            "source": "서울시설공단 공영주차장 FAQ (sisul.or.kr)",
        },
    ]
)


@st.cache_data(ttl=600)
def load_faq(keyword: str, category: str) -> pd.DataFrame:
    like = f"%{keyword}%"
    if category != "전체":
        return read_sql(
            "SELECT category, question, answer, source FROM FAQ "
            "WHERE category = :cat AND (question LIKE :kw OR answer LIKE :kw)",
            {"cat": category, "kw": like},
        )
    # 이 페이지 담당 카테고리만
    placeholders = ", ".join(f"'{c}'" for c in MY_CATEGORIES)
    return read_sql(
        f"SELECT category, question, answer, source FROM FAQ "
        f"WHERE category IN ({placeholders}) AND (question LIKE :kw OR answer LIKE :kw)",
        {"kw": like},
    )


col_kw, col_cat = st.columns([3, 1])
with col_kw:
    keyword = st.text_input("🔎 키워드로 검색 (예: 정기권, 환불, 감면)")
with col_cat:
    category = st.selectbox("카테고리", ["전체"] + MY_CATEGORIES)


def _filter_sample(df: pd.DataFrame) -> pd.DataFrame:
    out = df
    if category != "전체":
        out = out[out["category"] == category]
    if keyword:
        out = out[out["question"].str.contains(keyword, na=False) | out["answer"].str.contains(keyword, na=False)]
    return out


if not config.is_db_configured():
    st.info("DB 미설정 상태라 샘플 FAQ만 표시합니다.")
    result = _filter_sample(SAMPLE_FAQ)
else:
    try:
        result = load_faq(keyword, category)
    except Exception as exc:  # noqa: BLE001
        st.error(f"DB 조회 오류: {exc}")
        result = _filter_sample(SAMPLE_FAQ)

if result.empty:
    st.warning("검색 결과가 없습니다. collectors/faq_crawler_a.py로 수집 후 적재했는지 확인해주세요.")
else:
    st.caption(f"총 {len(result)}건")
    for _, row in result.iterrows():
        with st.expander(f"**[{row['category']}]** {row['question']}"):
            st.write(row["answer"])
            st.caption(f"📎 출처: {row['source']}")

st.divider()
st.caption("🔀 단속·견인·이의신청 관련 질문은 사이드바의 'FAQ 단속견인' 페이지(담당: 연주)를 확인하세요. 추후 한 페이지로 통합 예정입니다.")