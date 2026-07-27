"""
[담당: 연주 또는 은미] FAQ - 단속·견인·이의신청 페이지 (크롤링 B).

데이터 소스
    - 종로구시설관리공단 견인보관소 운영안내 (ijongno.co.kr/www/422, 정적)
    - 새올전자민원창구/응답소/국민신문고 안내 링크
    - 서울시 고시공고 '주정차' 키워드 (일시적 단속 완화, 집중단속 기간 등)
    -> collectors/faq_crawler_b.py 로 수집, FAQ 테이블에 적재
    -> category: 단속기준 / 신고방법 / 견인 / 이의신청 / 고시공고

⚠ 통합 계획: 이 페이지와 "FAQ - 이용안내"(은미)는 같은 FAQ 테이블을 쓰기 때문에,
나중에 category 필터만 합치면 한 페이지로 통합할 수 있다.
"""

import pandas as pd
import streamlit as st

import config
from common.db import read_sql
from common.ui import apply_style, hero

st.set_page_config(page_title="FAQ - 단속·견인", page_icon="🚛", layout="wide")
apply_style()
hero("🚛", "FAQ - 단속 · 견인 · 이의신청", "단속기준부터 견인 차량 인수, 이의신청 절차까지 안내합니다. (담당: 연주 또는 은미)")

# 이 페이지가 담당하는 카테고리 (크롤링 B 수집분)
MY_CATEGORIES = ["단속기준", "신고방법", "견인", "이의신청", "고시공고"]

SAMPLE_FAQ = pd.DataFrame(
    [
        {
            "category": "단속기준",
            "question": "불법 주정차로 단속되는 6대 구역은 어디인가요?",
            "answer": "소화전 5m 이내, 교차로 모퉁이 5m 이내, 버스정류소 10m 이내, 횡단보도, 인도, 어린이보호구역입니다.",
            "source": "샘플 데이터 (DB 미설정)",
        },
        {
            "category": "견인",
            "question": "불법주정차로 견인되면 차량은 어떻게 찾나요?",
            "answer": "신분증을 소지하고 견인보관소를 방문해 견인료+보관료를 납부하면 인수 가능합니다 (카드/계좌 결제 가능).",
            "source": "종로구시설관리공단 견인보관소 운영안내 (ijongno.co.kr/www/422)",
        },
        {
            "category": "이의신청",
            "question": "견인료·보관료에 이의가 있으면 어떻게 하나요?",
            "answer": "비용 납부 후 10일 이내 의견 진술 → 분기별 자체 심의 → 7일 이내 결과 통보 → 인정 시 7일 이내 환불 절차로 진행됩니다.",
            "source": "종로구시설관리공단 견인보관소 운영안내 (ijongno.co.kr/www/422)",
        },
        {
            "category": "고시공고",
            "question": "점심시간 단속유예 같은 일시적 단속 완화는 어디서 확인하나요?",
            "answer": "서울시 누리집(seoul.go.kr)·TOPIS(topis.seoul.go.kr) 고시공고에서 '주정차' 키워드로 확인할 수 있습니다. 종로구는 점심시간 주정차 단속유예 지역을 구 전역으로 확대했습니다 (2026.07 보도).",
            "source": "서울시 고시공고 / 연합뉴스 2026.07.08",
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
    placeholders = ", ".join(f"'{c}'" for c in MY_CATEGORIES)
    return read_sql(
        f"SELECT category, question, answer, source FROM FAQ "
        f"WHERE category IN ({placeholders}) AND (question LIKE :kw OR answer LIKE :kw)",
        {"kw": like},
    )


tab_faq, tab_calc, tab_appeal = st.tabs(["🔍 FAQ 검색", "🧮 과태료 계산기", "📝 이의신청 절차"])

# ---------------- FAQ 검색 ----------------
with tab_faq:
    col_kw, col_cat = st.columns([3, 1])
    with col_kw:
        keyword = st.text_input("🔎 키워드로 검색 (예: 견인, 이의신청, 단속유예)")
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
        st.warning("검색 결과가 없습니다. collectors/faq_crawler_b.py로 수집 후 적재했는지 확인해주세요.")
    else:
        st.caption(f"총 {len(result)}건")
        for _, row in result.iterrows():
            with st.expander(f"**[{row['category']}]** {row['question']}"):
                st.write(row["answer"])
                st.caption(f"📎 출처: {row['source']}")

# ---------------- 과태료 계산기 ----------------
with tab_calc:
    st.caption(
        "⚠ 아래 금액은 2026년 기준 언론/지자체 안내자료를 참고한 **근사치**입니다. "
        "실제 부과 금액은 관할 지자체 고지서를 확인하세요."
    )

    VEHICLE_TYPES = ["승용차", "승합차 / 4톤 이하 화물차", "이륜차"]
    ZONE_FEES = {
        "일반구역": {"승용차": 40000, "승합차 / 4톤 이하 화물차": 50000, "이륜차": 30000},
        "소화전 5m 이내": {"승용차": 90000, "승합차 / 4톤 이하 화물차": 90000, "이륜차": 60000},
        "버스정류소 10m 이내": {"승용차": 50000, "승합차 / 4톤 이하 화물차": 50000, "이륜차": 40000},
        "횡단보도": {"승용차": 50000, "승합차 / 4톤 이하 화물차": 50000, "이륜차": 40000},
        "교차로 모퉁이 5m 이내": {"승용차": 50000, "승합차 / 4톤 이하 화물차": 50000, "이륜차": 40000},
        "인도(보도)": {"승용차": 50000, "승합차 / 4톤 이하 화물차": 50000, "이륜차": 40000},
        "어린이보호구역 (08~20시)": {"승용차": 130000, "승합차 / 4톤 이하 화물차": 130000, "이륜차": 90000},
    }

    col1, col2, col3 = st.columns(3)
    with col1:
        vehicle = st.selectbox("차종", VEHICLE_TYPES)
    with col2:
        zone = st.selectbox("위반 구역 유형", list(ZONE_FEES.keys()))
    with col3:
        violation_count = st.number_input("올해 위반 횟수 (본 건 포함)", min_value=1, value=1, step=1)

    base_fee = ZONE_FEES[zone][vehicle]
    # 참고: 실제로는 지자체 조례에 따라 상습 위반 가산이 다르므로 이 배수는 단순 예시입니다.
    repeat_multiplier = 1.0 if violation_count <= 1 else 1.0 + 0.1 * (violation_count - 1)
    estimated_fee = int(base_fee * repeat_multiplier)

    st.write("")
    r1, r2, r3 = st.columns(3)
    r1.metric("기준 과태료", f"{base_fee:,}원")
    r2.metric("위반횟수 가중", f"×{repeat_multiplier:.1f}")
    r3.metric("💸 예상 과태료", f"{estimated_fee:,}원")

# ---------------- 이의신청 절차 ----------------
with tab_appeal:
    st.subheader("과태료 처분에 이의가 있을 때")
    st.markdown(
        """
        1. **의견진술** — 단속일로부터 **20일 이내**, 관할 지자체에 서면/방문으로 의견 제출
        2. **과태료 고지서 수령** — 의견진술이 반영되지 않으면 정식 고지서 발송
        3. **이의신청** — 고지서 수령일로부터 **60일 이내**, 방문 / 팩스 / 우편 중 택1로 제출
        4. **과태료 재판** — 이의신청도 받아들여지지 않으면 비송사건절차법에 따른 재판 진행
        """
    )
    st.caption("정확한 기한/절차는 관할 지자체 조례에 따라 다를 수 있으니 최종 확인이 필요합니다.")

    st.divider()
    st.subheader("🚛 견인된 경우 (부정주차·거주자우선주차 위반 포함)")
    st.markdown(
        """
        1. **비용 납부** — 견인료 + 보관료 납부 (카드/계좌 결제 가능)
        2. **의견 진술** — 납부 후 **10일 이내**
        3. **자체 심의** — 분기별로 진행
        4. **심의결과 통보** — 심의 후 **7일 이내**
        5. **비용 환불** — 환불 결정 시 **7일 이내** 처리
        """
    )
    st.caption("출처: 종로구시설관리공단 견인보관소 운영안내 (ijongno.co.kr/www/422)")

    st.divider()
    st.subheader("🔗 온라인 접수 채널")
    st.markdown(
        """
        - 종로구 새올전자민원창구 — jongno.eminwon.seoul.kr
        - 서울시 전자민원 응답소 — eungdapso.seoul.go.kr
        - 국민신문고 — epeople.go.kr
        """
    )
    st.caption(
        "위 사이트들은 로그인/본인인증이 필요한 실제 민원 접수 시스템이라 자동 조회 대신 "
        "바로가기로 안내합니다."
    )

st.divider()
st.caption("🔀 공영주차장 이용 관련 질문은 사이드바의 'FAQ 이용안내' 페이지(담당: 은미)를 확인하세요. 추후 한 페이지로 통합 예정입니다.")