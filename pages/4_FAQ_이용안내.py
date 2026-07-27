"""
[담당: 연주 또는 은미] FAQ 페이지.

데이터 소스: FAQ 테이블 (data/cleaned/FAQ_sample_.csv 를 loaders 로 적재)
    적재:  uv run python loaders/load_all.py --only FAQ

카테고리는 코드에 박아두지 않고 DB에 실제로 들어있는 값을 읽어서 쓴다.
예전에는 ["이용안내","결제오류","정기권","요금감면"] 로 고정돼 있었는데,
적재된 데이터의 카테고리가 바뀌면 필터에 걸리는 게 하나도 없어서
"검색 결과 없음"만 나왔다. 데이터가 바뀌어도 화면이 따라가도록 바꿨다.
"""

import pandas as pd
import streamlit as st

import config
from common.db import read_sql
from common.ui import apply_style, hero

st.set_page_config(page_title="FAQ - 이용안내", page_icon="💬", layout="wide")
apply_style()
hero("💬", "FAQ - 주정차 이용안내", "단속 기준, 과태료, 이의신청 등 궁금한 내용을 검색하세요. (담당: 연주 또는 은미)")

# DB가 없을 때 쓰는 샘플의 카테고리
SAMPLE_CATEGORIES = ["이용안내", "결제오류", "정기권", "요금감면"]

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
def load_categories() -> list[str]:
    """DB에 실제로 들어있는 카테고리 목록."""
    df = read_sql("SELECT DISTINCT category FROM FAQ WHERE category IS NOT NULL ORDER BY category")
    return df["category"].tolist()


@st.cache_data(ttl=600)
def load_faq(keyword: str, category: str) -> pd.DataFrame:
    like = f"%{keyword}%"
    if category != "전체":
        return read_sql(
            "SELECT category, question, answer, source FROM FAQ "
            "WHERE category = :cat AND (question LIKE :kw OR answer LIKE :kw)",
            {"cat": category, "kw": like},
        )
    return read_sql(
        "SELECT category, question, answer, source FROM FAQ "
        "WHERE question LIKE :kw OR answer LIKE :kw",
        {"kw": like},
    )


if config.is_db_configured():
    try:
        categories = load_categories()
    except Exception:  # noqa: BLE001 - DB가 죽어도 검색창은 그려준다
        categories = SAMPLE_CATEGORIES
else:
    categories = SAMPLE_CATEGORIES

col_kw, col_cat = st.columns([3, 1])
with col_kw:
    keyword = st.text_input("🔎 키워드로 검색 (예: 과태료, 견인, 이의신청)")
with col_cat:
    category = st.selectbox("카테고리", ["전체"] + categories)


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
    st.warning(
        "검색 결과가 없습니다. "
        "FAQ 데이터를 적재하려면 `uv run python loaders/load_all.py --only FAQ` 를 실행하세요."
    )
else:
    st.caption(f"총 {len(result)}건")
    for _, row in result.iterrows():
        with st.expander(f"**[{row['category']}]** {row['question']}"):
            st.write(row["answer"])
            st.caption(f"📎 출처: {row['source']}")

st.divider()
st.caption("🔀 개별 민원 사례는 사이드바의 '민원 게시판' 페이지에서 확인하세요.")