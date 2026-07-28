"""
[담당: 승희] 서울시 주차장 데이터 수집.

두 가지를 받아온다.

1) 주차장 목록 — 서울특별시 주차정보안내시스템 (parking.seoul.go.kr)
   사이트 지도 화면이 쓰는 내부 AJAX(SearchParkingBy.do)를 그대로 호출한다.
   자치구 단위로 공영·민영·부설을 전부 주고 **좌표를 100% 갖고 있다.**
   페이징이 없어서 자치구당 요청 1번이면 끝난다. (종로구 232곳)

2) 실시간 여유 — 서울시 실시간 주차정보 Open API (OA-21709)
   목록에는 총 주차면만 있어서 현재 주차 대수는 이 API로 받아 주차장코드로 붙인다.
   .env 의 SEOUL_OPENAPI_KEY 가 필요하고, 없으면 여유 정보 없이 동작한다.

실행
    uv run python collectors/seoul_parking.py                    # 종로구
    uv run python collectors/seoul_parking.py --district all     # 서울 25개구
    -> data/cleaned/parking_lot.csv (DB 적재용)

주의: 공개 웹서비스라 자치구 사이에 REQUEST_DELAY 만큼 쉬면서 순차 호출한다.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402

OUTPUT = ROOT / "data/cleaned/parking_lot.csv"
REQUEST_DELAY = 1.0

SEARCH_URL = "https://parking.seoul.go.kr/SearchParkingBy.do"
REALTIME_URL = "http://openapi.seoul.go.kr:8088/{key}/json/GetParkingInfo/1/1000/"

DISTRICTS = [
    "종로구", "중구", "용산구", "성동구", "광진구", "동대문구", "중랑구", "성북구",
    "강북구", "도봉구", "노원구", "은평구", "서대문구", "마포구", "양천구", "강서구",
    "구로구", "금천구", "영등포구", "동작구", "관악구", "서초구", "강남구", "송파구",
    "강동구",
]

# 최종 컬럼 (db/schema.sql 의 PARKING_LOT 과 같은 순서)
COLUMNS = [
    "parking_id", "parking_name", "lot_category", "lot_type", "operation_rule",
    "district", "address", "latitude", "longitude", "phone", "capacity",
    "pay_type", "base_fee", "base_time", "add_fee", "add_time",
    "day_max_fee", "monthly_fee",
    "weekday_start", "weekday_end", "weekend_start", "weekend_end",
    "holiday_start", "holiday_end", "source",
]

# 사이트의 parking_type -> (유형, 공영/민영)
# BP(국립현대미술관·정독도서관 등)는 공공기관 부설이라 공영으로 본다.
TYPE_MAP = {
    "NS": ("노상", "공영"), "NW": ("노외", "공영"), "BP": ("부설", "공영"),
    "NP": ("노외", "민영"), "BS": ("부설", "민영"),
}

# 사이트 응답 필드 -> COLUMNS
FIELD_MAP = {
    "parking_code": "parking_id", "parking_name": "parking_name",
    "address": "address", "capacity": "capacity", "phone": "phone",
    "rates": "base_fee", "time_rate": "base_time",
    "add_rates": "add_fee", "add_time_rate": "add_time",
    "day_maximum": "day_max_fee", "fulltime_monthly": "monthly_fee",
    "weekday_begin_time": "weekday_start", "weekday_end_time": "weekday_end",
    "weekend_begin_time": "weekend_start", "weekend_end_time": "weekend_end",
    "holiday_begin_time": "holiday_start", "holiday_end_time": "holiday_end",
}

# 숫자로 바꿀 컬럼 (빈 문자열은 결측 처리)
NUMERIC = [
    "capacity", "base_fee", "base_time", "add_fee", "add_time",
    "day_max_fee", "monthly_fee",
    "weekday_start", "weekday_end", "weekend_start", "weekend_end",
    "holiday_start", "holiday_end",
]


# ---------------------------------------------------------------------------
# 1) 주차장 목록
# ---------------------------------------------------------------------------
def _session() -> requests.Session:
    """사이트가 요구하는 헤더를 갖춘 세션 (첫 요청으로 세션 쿠키를 받아둔다)."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://parking.seoul.go.kr/",
    })
    session.get("https://parking.seoul.go.kr/", timeout=20)
    return session


def _center(row: dict) -> tuple[float | None, float | None]:
    """position_list의 중심 좌표. 노상주차장은 구간이 여러 개라 평균을 쓴다."""
    points = []
    for pos in row.get("position_list") or []:
        try:
            lat, lng = float(pos["lat"]), float(pos["lng"])
        except (KeyError, TypeError, ValueError):
            continue
        if lat and lng:  # 0.0은 정보 없음
            points.append((lat, lng))
    if not points:
        return None, None
    return (sum(p[0] for p in points) / len(points),
            sum(p[1] for p in points) / len(points))


def fetch_district(district: str, session: requests.Session) -> pd.DataFrame:
    """자치구 하나의 주차장 목록을 받아 COLUMNS 스키마로 반환."""
    payload = {"Gu": district, "Dong": "", "Keyword": "", "index": 1, "Type": "", "Rule": ""}
    try:
        body = session.post(SEARCH_URL, data=payload, timeout=30).json()
    except (requests.RequestException, ValueError) as exc:
        raise RuntimeError(f"{district} 수집 실패: {exc}") from exc

    if body.get("result_state") != "0000":
        raise RuntimeError(f"{district} 응답 오류: result_state={body.get('result_state')}")

    records = []
    for row in body.get("res_value", {}).get("parking_list", []):
        lat, lng = _center(row)
        lot_type, lot_category = TYPE_MAP.get(row.get("parking_type"), ("기타", "민영"))
        record = {target: row.get(source) for source, target in FIELD_MAP.items()}
        record.update({
            "latitude": lat, "longitude": lng,
            "lot_type": lot_type, "lot_category": lot_category,
            "district": district,
            "operation_rule": row.get("que_status_nm"),
            "pay_type": "유료" if row.get("pay_yn") == "Y" else "무료",
            "source": "seoul_site",
        })
        records.append(record)

    return _clean(pd.DataFrame(records))


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    """타입 정리 + COLUMNS 순서 맞추기."""
    if df.empty:
        return pd.DataFrame(columns=COLUMNS)

    out = df.copy()
    for col in ("parking_id", "parking_name", "address"):
        out[col] = out[col].astype(str).str.strip()
    for col in NUMERIC:
        out[col] = pd.to_numeric(
            out[col].astype(str).str.strip().replace("", pd.NA), errors="coerce"
        ).round().astype("Int64")

    for col in COLUMNS:
        if col not in out.columns:
            out[col] = pd.NA
    return out[COLUMNS]


def collect(districts: list[str] | str = "종로구") -> pd.DataFrame:
    """자치구 목록을 순서대로 수집해 하나의 DataFrame으로."""
    if isinstance(districts, str):
        districts = DISTRICTS if districts == "all" else [districts]

    session = _session()
    frames = []
    for i, district in enumerate(districts):
        if i:
            time.sleep(REQUEST_DELAY)
        frames.append(fetch_district(district, session))

    if not frames:
        return pd.DataFrame(columns=COLUMNS)
    result = pd.concat(frames, ignore_index=True)
    # parking_id 가 PK라서 혹시라도 겹치면 먼저 나온 행만 남긴다
    return result.drop_duplicates(subset="parking_id").reset_index(drop=True)


# ---------------------------------------------------------------------------
# 2) 실시간 여유
# ---------------------------------------------------------------------------
def fetch_realtime() -> pd.DataFrame:
    """시영주차장의 현재 주차 대수. 키가 없거나 실패하면 빈 DataFrame.

    반환: parking_id, capacity, now_parked, available, updated_at
    """
    empty = pd.DataFrame(
        columns=["parking_id", "capacity", "now_parked", "available", "updated_at"]
    )
    if not config.SEOUL_OPENAPI_KEY:
        return empty

    try:
        body = requests.get(
            REALTIME_URL.format(key=config.SEOUL_OPENAPI_KEY), timeout=15
        ).json()
    except (requests.RequestException, ValueError):
        return empty

    rows = body.get("GetParkingInfo", {}).get("row", [])
    if not rows:
        return empty

    df = pd.DataFrame(rows)
    df = df.rename(columns={
        "PKLT_CD": "parking_id", "TPKCT": "capacity",
        "NOW_PRK_VHCL_CNT": "now_parked", "NOW_PRK_VHCL_UPDT_TM": "updated_at",
    })
    df["parking_id"] = df["parking_id"].astype(str).str.strip()
    for col in ("capacity", "now_parked"):
        df[col] = pd.to_numeric(df[col], errors="coerce").round().astype("Int64")
    df["available"] = (df["capacity"] - df["now_parked"]).clip(lower=0)
    return df[["parking_id", "capacity", "now_parked", "available", "updated_at"]]


def attach_realtime(lots: pd.DataFrame, realtime: pd.DataFrame) -> pd.DataFrame:
    """주차장 목록에 실시간 여유를 주차장코드로 붙인다.

    총 주차면(capacity)도 실시간 값으로 덮어쓴다. 목록의 총 주차면이 오래돼서
    실제와 다른 경우가 있는데(총 1면인데 여유 7면), 그대로 두면 여유 점수가 1을 넘는다.
    """
    out = lots.copy()
    out["parking_id"] = out["parking_id"].astype(str).str.strip()

    if realtime.empty:
        out["now_parked"] = pd.Series(pd.NA, index=out.index, dtype="Int64")
        out["available"] = pd.Series(pd.NA, index=out.index, dtype="Int64")
        out["updated_at"] = pd.NA
        return out

    live = realtime.rename(columns={"capacity": "_live_capacity"})
    out = out.merge(live, on="parking_id", how="left")
    base = pd.to_numeric(out["capacity"], errors="coerce").astype("Int64")
    out["capacity"] = out["_live_capacity"].fillna(base)
    return out.drop(columns="_live_capacity")


# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="서울시 주차장 수집")
    parser.add_argument("--district", default="종로구",
                        help="자치구명, 또는 'all'로 서울 25개구 (기본: 종로구)")
    parser.add_argument("--out", default=str(OUTPUT), help="저장 경로")
    args = parser.parse_args()

    lots = collect(args.district)
    print(f"수집: {len(lots):,}곳")
    print(lots.groupby(["lot_category", "lot_type"]).size().to_string())
    with_coord = lots[["latitude", "longitude"]].notna().all(axis=1).sum()
    print(f"좌표 보유: {with_coord:,}/{len(lots):,}곳 ({with_coord / len(lots) * 100:.1f}%)")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lots.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"저장 완료 -> {out_path}")


if __name__ == "__main__":
    main()
