"""
[담당: 은미] FAQ 크롤링 A - 공영주차장 이용안내 계열 (BeautifulSoup + requests).

데이터 소스: 서울시설공단 공영주차장 FAQ (sisul.or.kr)
    https://www.sisul.or.kr/open_content/parking/bbs/bbsMsgList.do?bcd=faq&cate1=parking&cate2=03
    -> 완전한 정적 HTML 게시판이라 requests+bs4만으로 목록/상세 수집 가능 (실제 확인됨).
    -> cate2 값으로 카테고리가 나뉨(01 환경설정, 02 결제오류, 03 정기권, 04 요금감면, 05 이용안내).

수집 결과는 FAQ 테이블의 category 컬럼에 이용안내/결제오류/정기권/요금감면으로
태깅되어 저장되고, "FAQ - 이용안내" 페이지(pages/4_FAQ_이용안내.py)에서 사용한다.

실행
    uv run python collectors/faq_crawler_a.py
    uv run python loaders/load_to_db.py --csv data/raw/faq_a_raw.csv --table FAQ --if-exists append
"""

import re
import time

import pandas as pd
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

SISUL_LIST_URL = "https://www.sisul.or.kr/open_content/parking/bbs/bbsMsgList.do"
SISUL_DETAIL_URL = "https://www.sisul.or.kr/open_content/parking/bbs/bbsMsgDetail.do"

# cate2 값(사이트 좌측 탭) -> 우리 서비스 FAQ 카테고리로 매핑
SISUL_CATEGORIES = {
    "01": "이용안내",  # 환경설정
    "02": "결제오류",
    "03": "정기권",
    "04": "요금감면",
    "05": "이용안내",
}


def crawl_sisul_faq(max_pages_per_cate: int = 3) -> list[dict]:
    """서울시설공단 공영주차장 FAQ 게시판을 카테고리별로 순회하며 수집."""
    rows: list[dict] = []

    for cate2, category in SISUL_CATEGORIES.items():
        for page in range(1, max_pages_per_cate + 1):
            res = requests.get(
                SISUL_LIST_URL,
                params={"bcd": "faq", "cate1": "parking", "cate2": cate2, "pgno": page},
                headers=HEADERS,
                timeout=10,
            )
            if res.status_code != 200:
                break

            soup = BeautifulSoup(res.text, "html.parser")
            # 마크업(클래스명)이 바뀌어도 안전하도록, 상세 링크(href)의 패턴으로 직접 찾는다.
            links = [
                a
                for a in soup.find_all("a", href=True)
                if "bbsMsgDetail.do" in a["href"] and "msg_seq=" in a["href"]
            ]
            if not links:
                break

            seen_ids: set[str] = set()
            found_new = False
            for a in links:
                match = re.search(r"msg_seq=(\d+)", a["href"])
                if not match:
                    continue
                msg_seq = match.group(1)
                if msg_seq in seen_ids:
                    continue
                seen_ids.add(msg_seq)

                question = a.get_text(strip=True)
                if not question.startswith("Q"):
                    continue
                found_new = True

                answer = _crawl_detail(msg_seq, cate2)
                if answer:
                    rows.append(
                        {
                            "category": category,
                            "question": question.lstrip("Q").lstrip(".").strip(),
                            "answer": answer,
                            "source": (
                                f"{SISUL_DETAIL_URL}?msg_seq={msg_seq}"
                                f"&cate1=parking&cate2={cate2}&bcd=faq"
                            ),
                        }
                    )
                time.sleep(0.3)  # 서버 부담 완화

            if not found_new:
                break

    return rows


def _crawl_detail(msg_seq: str, cate2: str) -> str | None:
    res = requests.get(
        SISUL_DETAIL_URL,
        params={"msg_seq": msg_seq, "cate1": "parking", "cate2": cate2, "bcd": "faq"},
        headers=HEADERS,
        timeout=10,
    )
    if res.status_code != 200:
        return None
    soup = BeautifulSoup(res.text, "html.parser")
    # 상세 페이지 본문 컨테이너 후보들 (은미가 개발자도구로 실제 클래스명을 확인해서
    # 더 좁혀도 된다. 못 찾으면 #contents 전체 텍스트를 사용).
    content = soup.select_one(".bbs-view, .board-view, .view-cont") or soup.select_one("#contents")
    return content.get_text(" ", strip=True) if content else None


if __name__ == "__main__":
    rows = crawl_sisul_faq()
    df = pd.DataFrame(rows)
    df.to_csv("data/raw/faq_a_raw.csv", index=False, encoding="utf-8-sig")
    print(f"{len(df)}건 수집 완료 -> data/raw/faq_a_raw.csv")