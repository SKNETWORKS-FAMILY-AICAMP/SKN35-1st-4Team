"""
[담당: 주정차 단속 알림 서비스팀]
종로구 주정차 단속/완화 고시공고 경량 크롤러 (httpx + BeautifulSoup)

수집 대상:
1. 서울시 대표 누리집 (seoul.go.kr)
2. 서울교통정보센터 TOPIS (topis.seoul.go.kr)
3. 종로구청 누리집 (jongno.go.kr)

필요 패키지 설치:
    uv add httpx beautifulsoup4 pandas
"""

import asyncio
import hashlib
import os
import subprocess
from datetime import datetime
import pandas as pd
from bs4 import BeautifulSoup
import httpx

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

SEOUL_NOTICE_URL = "https://www.seoul.go.kr/news/news_notice.do"
TOPIS_NOTICE_URL = "https://topis.seoul.go.kr/notice/selectNoticeList.do"
JONGNO_NOTICE_URL = "https://www.jongno.go.kr/portal/bbs/selectBbsList.do"


def generate_notice_id(source: str, title: str, date: str) -> str:
    """공고의 중복 식별을 위한 고유 Hash 생성"""
    raw_str = f"{source}_{title}_{date}"
    return hashlib.md5(raw_str.encode("utf-8")).hexdigest()


def classify_category(title: str) -> str:
    """공고 제목 기반 카테고리 태깅"""
    if any(k in title for k in ["완화", "유예"]):
        return "단속완화"
    elif any(k in title for k in ["집중", "단속"]):
        return "집중단속"
    elif any(k in title for k in ["CCTV", "고시", "지정"]):
        return "지정고시"
    return "기타공고"


async def crawl_seoul_jongno_notices(client: httpx.AsyncClient) -> list[dict]:
    """1. 서울시 대표 누리집 고시공고 수집 (Request)"""
    results = []
    print("[1/3] 서울시 대표 누리집(고시공고) 크롤링 시작...")

    params = {
        "srchTxt": "종로구 주정차"
    }

    try:
        response = await client.get(SEOUL_NOTICE_URL, params=params, timeout=15.0)
        soup = BeautifulSoup(response.text, "html.parser")
        rows = soup.select("table tbody tr, ul.board-list > li")

        for row in rows:
            title_el = row.select_one("a.title, td.subject a, a")
            date_el = row.select_one("td.date, span.date, .reg-date")

            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            date = date_el.get_text(strip=True) if date_el else datetime.now().strftime("%Y-%m-%d")

            if ("종로" in title or "전체" in title) and any(k in title for k in ["주정차", "단속", "완화", "유예"]):
                link = title_el.get("href", "")
                if link and not link.startswith("http") and not link.startswith("javascript"):
                    link = f"https://www.seoul.go.kr{link}"

                results.append({
                    "notice_id": generate_notice_id("SEOUL", title, date),
                    "source": "서울시청",
                    "region": "종로구",
                    "category": classify_category(title),
                    "title": title,
                    "date": date,
                    "link": link,
                    "crawled_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
    except Exception as e:
        print(f"서울시 고시공고 수집 중 오류: {e}")

    return results


async def crawl_topis_notices(client: httpx.AsyncClient) -> list[dict]:
    """2. 서울교통정보센터(TOPIS) 고시공고 수집 (Request)"""
    results = []
    print("[2/3] 서울교통정보센터(TOPIS) 크롤링 시작...")

    params = {
        "searchWrd": "주정차"
    }

    try:
        response = await client.get(TOPIS_NOTICE_URL, params=params, timeout=15.0)
        soup = BeautifulSoup(response.text, "html.parser")
        rows = soup.select("table tbody tr, ul.notice_list > li")

        for row in rows:
            title_el = row.select_one("td.title a, td.subject a, a")
            date_el = row.select_one("td.date, span.date")

            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            date = date_el.get_text(strip=True) if date_el else datetime.now().strftime("%Y-%m-%d")

            if any(k in title for k in ["주정차", "단속", "완화", "종로"]):
                link = title_el.get("href", "")
                if link and not link.startswith("http") and not link.startswith("javascript"):
                    link = f"https://topis.seoul.go.kr{link}"

                results.append({
                    "notice_id": generate_notice_id("TOPIS", title, date),
                    "source": "TOPIS",
                    "region": "종로구" if "종로" in title else "서울시 전체",
                    "category": classify_category(title),
                    "title": title,
                    "date": date,
                    "link": link,
                    "crawled_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
    except Exception as e:
        print(f"TOPIS 수집 중 오류: {e}")

    return results


async def crawl_jongno_portal_notices(client: httpx.AsyncClient) -> list[dict]:
    """3. 종로구청 누리집 고시공고 수집 (Request)"""
    results = []
    print("[3/3] 종로구청 누리집(고시공고) 크롤링 시작...")

    params = {
        "bbsId": "BBSMSTR_000000000021",
        "menuNo": "1754",
        "searchWrd": "주정차"
    }

    try:
        response = await client.get(JONGNO_NOTICE_URL, params=params, timeout=15.0)
        soup = BeautifulSoup(response.text, "html.parser")
        rows = soup.select("table.bbs_default tbody tr, table.p-table tbody tr")

        for row in rows:
            title_el = row.select_one("td.subject a, td.p-table__subject a, a")
            date_el = row.select_one("td.date, td:nth-child(5)")

            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            date = date_el.get_text(strip=True) if date_el else datetime.now().strftime("%Y-%m-%d")

            if any(k in title for k in ["주정차", "단속", "완화", "유예", "스마트", "CCTV"]):
                link = title_el.get("href", "")
                if link and not link.startswith("http") and not link.startswith("javascript"):
                    link = f"https://www.jongno.go.kr{link}"

                results.append({
                    "notice_id": generate_notice_id("JONGNO", title, date),
                    "source": "종로구청",
                    "region": "종로구",
                    "category": classify_category(title),
                    "title": title,
                    "date": date,
                    "link": link,
                    "crawled_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
    except Exception as e:
        print(f"종로구청 고시공고 수집 중 오류: {e}")

    return results


async def main_crawler() -> list[dict]:
    """httpx 비동기 클라이언트 기반 통합 수집"""
    all_notices = []

    # SSL 인증서 검증 무시 및 User-Agent 설정
    async with httpx.AsyncClient(headers=HEADERS, verify=False, follow_redirects=True) as client:
        # 1. 서울시청 수집
        seoul_data = await crawl_seoul_jongno_notices(client)
        all_notices.extend(seoul_data)

        # 2. TOPIS 수집
        topis_data = await crawl_topis_notices(client)
        all_notices.extend(topis_data)

        # 3. 종로구청 수집
        jongno_data = await crawl_jongno_portal_notices(client)
        all_notices.extend(jongno_data)

    return all_notices


if __name__ == "__main__":
    os.makedirs("data/raw", exist_ok=True)

    data = asyncio.run(main_crawler())

    if data:
        df = pd.DataFrame(data)

        output_path = "data/raw/jongno_parking_notices.csv"

        # 기존 CSV 파일이 있을 경우 병합하여 실시간/누적 업데이트
        if os.path.exists(output_path):
            existing_df = pd.read_csv(output_path)
            df = pd.concat([existing_df, df], ignore_index=True)

        # notice_id 기준 중복 제거
        df.drop_duplicates(subset=["notice_id"], keep="first", inplace=True)

        # CSV 파일 저장
        df.to_csv(output_path, index=False, encoding="utf-8-sig")
        print(f"✅ 총 {len(df)}건의 주정차 관련 공고 누적/수집 완료 -> {output_path}")

        # DB 저장 스크립트 연동 (필요 시 주석 해제)
        # subprocess.run(["uv", "run", "python", "loaders/load_to_db.py", "--csv", output_path, "--table", "PARKING_NOTICES", "--if-exists", "append"])
    else:
        print("⚠️ 수집된 새로운 공고가 없습니다.")