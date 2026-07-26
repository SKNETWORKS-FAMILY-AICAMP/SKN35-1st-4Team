"""
[담당: 승희] 서울특별시 주차정보안내시스템(parking.seoul.go.kr) 수집기.

왜 이걸 만들었나
    서울시 공영주차장 안내 정보 CSV(OA-13122)는 **좌표가 850곳 중 117곳(14%)** 뿐이라
    지도에 마커가 거의 안 찍혔다. 그리고 공영만 있어서 민영은 아예 없었다.
    이 사이트의 검색 API는 자치구 단위로 공영·민영·부설을 전부 주고,
    **좌표(position_list)를 100% 갖고 있다.** 종로구 기준 43곳 -> 232곳.

동작 방식
    사이트가 지도 화면에서 쓰는 내부 AJAX(SearchParkingBy.do)를 그대로 호출한다.
    페이징이 없어서 자치구 하나당 요청 1번이면 전부 받아진다.
        POST https://parking.seoul.go.kr/SearchParkingBy.do
        data: Gu=종로구, Dong=, Keyword=, index=1, Type=, Rule=

주차장 구분 (parking_type)
    NS 노상(공영)  NW 노외(공영)  BP 부설(공공기관)
    NP 노외(민영)  BS 부설(민영)

실행
    uv run python collectors/seoul_parking_crawler.py --district 종로구
    uv run python collectors/seoul_parking_crawler.py --district all      # 서울 25개구
    -> data/cleaned/site_parking.csv (+ data/raw/seoul_site/<구>.json 원본 보관)

주의: 공개 웹서비스라 요청 간 간격(REQUEST_DELAY)을 두고 순차 호출한다.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collectors.merge_parking import to_table_schema as _final_schema  # noqa: E402

BASE_URL = "https://parking.seoul.go.kr"
SEARCH_URL = f"{BASE_URL}/SearchParkingBy.do"
RAW_DIR = ROOT / "data/raw/seoul_site"
DEFAULT_OUTPUT = ROOT / "data/cleaned/site_parking.csv"
REQUEST_DELAY = 1.0  # 초 - 서버 부담을 줄이기 위한 요청 간격

DISTRICTS = [
    "종로구", "중구", "용산구", "성동구", "광진구", "동대문구", "중랑구", "성북구",
    "강북구", "도봉구", "노원구", "은평구", "서대문구", "마포구", "양천구", "강서구",
    "구로구", "금천구", "영등포구", "동작구", "관악구", "서초구", "강남구", "송파구",
    "강동구",
]

# parking_type -> (주차장 유형, 공영/민영)
#   BP(국립현대미술관·정독도서관 등)는 공공기관 부설이라 공영으로 분류한다.
TYPE_MAP = {
    "NS": ("노상", "공영"),
    "NW": ("노외", "공영"),
    "BP": ("부설", "공영"),
    "NP": ("노외", "민영"),
    "BS": ("부설", "민영"),
}

# 응답 필드 -> 통합 스키마 (collectors/merge_parking.TABLE_COLUMNS)
FIELD_MAP = {
    "parking_code": "parking_id",
    "parking_name": "parking_name",
    "address": "address",
    "capacity": "capacity",
    "phone": "phone",
    "rates": "base_fee",
    "time_rate": "base_time",
    "add_rates": "add_fee",
    "add_time_rate": "add_time",
    "day_maximum": "day_max_fee",
    "fulltime_monthly": "monthly_fee",
    "weekday_begin_time": "weekday_start",
    "weekday_end_time": "weekday_end",
    "weekend_begin_time": "weekend_start",
    "weekend_end_time": "weekend_end",
    "holiday_begin_time": "holiday_start",
    "holiday_end_time": "holiday_end",
}
INT_COLUMNS = [
    "capacity", "base_fee", "base_time", "add_fee", "add_time",
    "day_max_fee", "monthly_fee",
    "weekday_start", "weekday_end", "weekend_start", "weekend_end",
    "holiday_start", "holiday_end",
]


# ---------------------------------------------------------------------------
# 1) 수집
# ---------------------------------------------------------------------------
def make_session() -> requests.Session:
    """사이트가 요구하는 헤더를 갖춘 세션. 첫 요청으로 세션 쿠키를 받아둔다."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"{BASE_URL}/",
    })
    session.get(BASE_URL, timeout=20)
    return session


def fetch_district(district: str, session: requests.Session | None = None,
                   timeout: int = 30) -> list[dict]:
    """자치구 하나의 주차장 목록(raw JSON 레코드)을 전부 받아온다."""
    session = session or make_session()
    payload = {"Gu": district, "Dong": "", "Keyword": "", "index": 1, "Type": "", "Rule": ""}

    try:
        response = session.post(SEARCH_URL, data=payload, timeout=timeout)
        body = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise RuntimeError(f"{district} 수집 실패: {exc}") from exc

    if body.get("result_state") != "0000":
        raise RuntimeError(f"{district} 응답 오류: result_state={body.get('result_state')}")

    return body.get("res_value", {}).get("parking_list", [])


def save_raw(district: str, rows: list[dict]) -> Path:
    """원본 JSON을 보관한다 (사이트가 바뀌어도 정제를 다시 돌릴 수 있도록)."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"{district}.json"
    path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return path


def load_raw(district: str) -> list[dict] | None:
    path = RAW_DIR / f"{district}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------------------
# 2) 정제
# ---------------------------------------------------------------------------
def _first_position(row: dict) -> tuple[float | None, float | None]:
    """position_list의 첫 좌표. 노상주차장은 구간이 여러 개라 평균(중심점)을 쓴다."""
    positions = row.get("position_list") or []
    points = []
    for pos in positions:
        try:
            lat, lng = float(pos.get("lat")), float(pos.get("lng"))
        except (TypeError, ValueError):
            continue
        if lat and lng:  # 0.0은 정보 없음
            points.append((lat, lng))

    if not points:
        return None, None
    return (sum(p[0] for p in points) / len(points),
            sum(p[1] for p in points) / len(points))


def to_table_schema(rows: list[dict], district: str | None = None) -> pd.DataFrame:
    """raw JSON 레코드를 통합 테이블 스키마로 변환."""
    if not rows:
        return _final_schema(pd.DataFrame())

    records = []
    for row in rows:
        lat, lng = _first_position(row)
        lot_type, lot_category = TYPE_MAP.get(row.get("parking_type"), ("기타", "민영"))

        record = {target: row.get(source) for source, target in FIELD_MAP.items()}
        record.update({
            "latitude": lat,
            "longitude": lng,
            "lot_type": lot_type,
            "lot_category": lot_category,
            "operation_rule": row.get("que_status_nm"),
            "pay_type": "유료" if row.get("pay_yn") == "Y" else "무료",
            "source": "seoul_site",
        })
        records.append(record)

    out = pd.DataFrame(records)
    out["parking_id"] = out["parking_id"].astype(str).str.strip()
    out["parking_name"] = out["parking_name"].astype(str).str.strip()
    out["address"] = out["address"].astype(str).str.strip()

    # 빈 문자열은 결측으로 (요금 미공개 주차장이 꽤 있다)
    for col in INT_COLUMNS:
        out[col] = pd.to_numeric(
            out[col].astype(str).str.strip().replace("", pd.NA), errors="coerce"
        ).round().astype("Int64")

    out["district"] = district or out["address"].str.extract(
        r"(?:^|\s)([가-힣]+구)(?=\s|$)", expand=False
    )
    return _final_schema(out)


def collect(districts: list[str] | str = "종로구", use_cache: bool = True,
            refresh: bool = False) -> pd.DataFrame:
    """자치구 목록을 수집해 하나의 DataFrame으로. 원본 JSON 캐시를 우선 사용한다."""
    if isinstance(districts, str):
        districts = DISTRICTS if districts == "all" else [districts]

    session: requests.Session | None = None
    frames = []
    for i, district in enumerate(districts):
        rows = None if refresh else (load_raw(district) if use_cache else None)
        if rows is None:
            if session is None:
                session = make_session()
            elif i:
                time.sleep(REQUEST_DELAY)
            rows = fetch_district(district, session)
            save_raw(district, rows)
        frames.append(to_table_schema(rows, district))

    if not frames:
        return _final_schema(pd.DataFrame())
    return pd.concat(frames, ignore_index=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="서울시 주차정보안내시스템 수집")
    parser.add_argument("--district", default="종로구",
                        help="자치구명, 또는 'all'로 서울 25개구 전체 (기본: 종로구)")
    parser.add_argument("--refresh", action="store_true", help="캐시 무시하고 다시 받기")
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT), help="저장 경로")
    args = parser.parse_args()

    result = collect(args.district, refresh=args.refresh)
    print(f"수집: {len(result):,}곳")
    if not result.empty:
        print(result.groupby(["lot_category", "lot_type"]).size().to_string())
        with_coord = result[["latitude", "longitude"]].notna().all(axis=1).sum()
        print(f"좌표 보유: {with_coord:,}/{len(result):,}곳 "
              f"({with_coord / len(result) * 100:.1f}%)")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"저장 완료 -> {out_path}")


if __name__ == "__main__":
    main()
