"""
[담당: 연주] FAQ 크롤링 B - 단속·견인·이의신청 계열 (BeautifulSoup + requests).

데이터 소스 (실제로 열어보고 확인한 결과):
1) 종로구시설관리공단 견인보관소 운영안내 (https://www.ijongno.co.kr/www/422)
   -> 정적 단일 페이지. 견인료/보관료 표, 이의제기 절차, 관련법규 텍스트 확인됨.
   -> FAQ 게시판이 아니라 안내문이라, 소제목(h4/h5) 단위로 잘라 Q&A로 변환.
2) 새올전자민원창구/응답소/국민신문고
   -> 로그인 필요한 실제 민원 시스템이라 자동 크롤링 대신 안내 링크로 수록(MINWON_LINKS).
3) 서울시 고시공고 '주정차' 키워드 (일시적 단속 완화, 집중단속 기간 등)
   -> seoul.go.kr 고시공고 게시판은 JS 렌더링이라 requests로는 본문이 비어 온다.
      아래 crawl_gosi()에 Selenium 전환용 골격만 잡아뒀다 (TODO 참고).

수집 결과는 FAQ 테이블의 category 컬럼에 견인/이의신청/고시공고로 태깅되어
"FAQ - 단속·견인·이의신청" 페이지(pages/5_FAQ_단속견인.py)에서 사용한다.

실행
    uv run python collectors/faq_crawler_b.py
    uv run python loaders/load_to_db.py --csv data/raw/faq_b_raw.csv --table FAQ --if-exists append
"""

import pandas as pd
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

# ---------------------------------------------------------------------------
# 1) 종로구시설관리공단 견인보관소 운영안내 (정적 페이지, 크롤링 확인됨)
# ---------------------------------------------------------------------------
IJONGNO_TOWING_URL = "https://www.ijongno.co.kr/www/422"


def crawl_ijongno_towing() -> list[dict]:
    """운영안내 페이지를 소제목 단위로 잘라 질문=소제목, 답변=본문 형태로 변환."""
    res = requests.get(IJONGNO_TOWING_URL, headers=HEADERS, timeout=10)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")

    rows: list[dict] = []
    for h in soup.select("h4, h5"):
        title = h.get_text(strip=True)
        if not title:
            continue

        body_parts: list[str] = []
        for sib in h.find_next_siblings():
            if sib.name in ("h4", "h5"):
                break
            text = sib.get_text(" ", strip=True)
            if text:
                body_parts.append(text)

        if body_parts:
            category = "이의신청" if "이의" in title else "견인"
            rows.append(
                {
                    "category": category,
                    "question": title,
                    "answer": " ".join(body_parts)[:2000],  # 표/법규 나열이 길어 상한을 둠
                    "source": IJONGNO_TOWING_URL,
                }
            )
    return rows


# ---------------------------------------------------------------------------
# 2) 민원 접수 채널 - 자동 크롤링 대신 안내 링크로 수록
# ---------------------------------------------------------------------------
MINWON_LINKS: list[dict] = [
    {
        "category": "이의신청",
        "question": "불법주정차 과태료에 이의신청/의견진술을 하고 싶어요.",
        "answer": (
            "종로구 새올전자민원창구(jongno.eminwon.seoul.kr), 서울시 전자민원 응답소"
            "(eungdapso.seoul.go.kr), 국민신문고(epeople.go.kr) 중 편한 곳에서 온라인으로"
            " 접수할 수 있습니다. 단속일로부터 의견진술은 20일 이내, 정식 고지서 수령 후"
            " 이의신청은 60일 이내로 기한이 정해져 있으니 반드시 확인하세요."
        ),
        "source": "jongno.eminwon.seoul.kr / eungdapso.seoul.go.kr / epeople.go.kr",
    },
    {
        "category": "고시공고",
        "question": "일시적인 단속 완화(점심시간 단속유예 등) 정보는 어디서 확인하나요?",
        "answer": (
            "서울시 누리집(seoul.go.kr)과 서울교통정보센터(TOPIS, topis.seoul.go.kr)의"
            " 고시공고 게시판에서 '주정차' 키워드로 확인할 수 있습니다. 예: 종로구는"
            " 점심시간 주정차 단속유예 지역을 구 전역으로 확대했습니다 (2026.07 보도)."
        ),
        "source": "topis.seoul.go.kr / seoul.go.kr (고시공고)",
    },
]


# ---------------------------------------------------------------------------
# 3) 서울시 고시공고 '주정차' 키워드 (JS 렌더링 -> Selenium 필요)
# ---------------------------------------------------------------------------
def crawl_gosi() -> list[dict]:
    """서울시 고시공고에서 '주정차' 키워드 공고를 수집 (TODO: Selenium 구현).

    seoul.go.kr 고시공고는 requests로 요청하면 본문이 비어 오는 것을 확인했다.
    연주가 구현할 때 순서:
        1) selenium으로 고시공고 검색 페이지 열기 ('주정차' 검색)
        2) driver.page_source를 BeautifulSoup에 넘겨 제목/날짜/링크 추출
        3) {"category": "고시공고", "question": 제목, "answer": 요약, "source": 링크}
           형태로 반환
    참고 구현 패턴: 이전 스캐폴드의 region_rule_crawler.py (Selenium은 렌더링만,
    파싱은 항상 BeautifulSoup에 넘기는 구조).
    """
    print("TODO(연주): 서울시 고시공고 Selenium 크롤링 구현 예정 - 현재는 빈 목록 반환")
    return []


def crawl_all() -> pd.DataFrame:
    rows: list[dict] = []

    try:
        towing = crawl_ijongno_towing()
        print(f"[ijongno.co.kr] {len(towing)}건 수집")
        rows.extend(towing)
    except Exception as exc:  # noqa: BLE001
        print(f"[ijongno.co.kr] 수집 실패: {exc}")

    rows.extend(MINWON_LINKS)
    rows.extend(crawl_gosi())
    return pd.DataFrame(rows)


if __name__ == "__main__":
    df = crawl_all()
    df.to_csv("data/raw/faq_b_raw.csv", index=False, encoding="utf-8-sig")
    print(f"총 {len(df)}건 수집 완료 -> data/raw/faq_b_raw.csv")