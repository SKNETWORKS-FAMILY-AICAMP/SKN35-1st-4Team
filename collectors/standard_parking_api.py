"""
[담당: 승희] 전국주차장정보표준데이터 수집 · 정제 (민영 · 부설 주차장 확보용).

서울시 공영주차장 데이터(OA-13122)에는 **공영만** 있다.
민영·부설 주차장까지 검색하려면 행정안전부 표준데이터가 필요하다.
핵심 컬럼은 `주차장구분`(공영/민영)과 `주차장유형`(노상/노외/부설).

받는 방법 두 가지 (둘 중 아무거나)
    1) CSV 다운로드  : https://www.data.go.kr/data/15012896/standard.do
                       -> data/raw/national_parking.csv 로 저장
    2) 오픈 API 호출 : .env 에 DATA_GO_KR_API_KEY 를 넣고 --api 옵션 사용

실행
    uv run python collectors/standard_parking_api.py --district 종로구
    uv run python collectors/standard_parking_api.py --district 종로구 --api
    -> data/cleaned/standard_parking.csv 생성

CSV(한글 헤더)든 API(영문 키)든 결과 스키마는 공영 수집기와 동일하게 맞춘다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # `python collectors/...` 로 직접 실행해도 config를 찾도록

import config  # noqa: E402

RAW_CANDIDATES = (
    ROOT / "data/raw/national_parking.csv",
    ROOT / "data/raw/전국주차장정보표준데이터.csv",
)
DEFAULT_OUTPUT = ROOT / "data/cleaned/standard_parking.csv"

API_URL = "https://api.data.go.kr/openapi/tn_pubr_prkplce_info_api"
API_PAGE_SIZE = 1000

# CSV(한글 헤더) -> 통합 스키마
CSV_COLUMN_MAP = {
    "주차장관리번호": "parking_id",
    "주차장명": "parking_name",
    "주차장구분": "lot_category",
    "주차장유형": "lot_type",
    "소재지도로명주소": "road_address",
    "소재지지번주소": "address",
    "주차구획수": "capacity",
    "운영요일": "operation_rule",
    "평일운영시작시각": "weekday_start",
    "평일운영종료시각": "weekday_end",
    "토요일운영시작시각": "weekend_start",
    "토요일운영종료시각": "weekend_end",
    "공휴일운영시작시각": "holiday_start",
    "공휴일운영종료시각": "holiday_end",
    "요금정보": "pay_type",
    "주차기본시간": "base_time",
    "주차기본요금": "base_fee",
    "추가단위시간": "add_time",
    "추가단위요금": "add_fee",
    "일주차권요금": "day_max_fee",
    "월정기권요금": "monthly_fee",
    "결제방법": "pay_method",
    "관리기관명": "operator",
    "전화번호": "phone",
    "위도": "latitude",
    "경도": "longitude",
}

# API(영문 키) -> 통합 스키마. 같은 데이터셋이라 의미는 CSV와 1:1로 대응된다.
API_COLUMN_MAP = {
    "prkplceNo": "parking_id",
    "prkplceNm": "parking_name",
    "prkplceSe": "lot_category",
    "prkplceType": "lot_type",
    "rdnmadr": "road_address",
    "lnmadr": "address",
    "prkcmprt": "capacity",
    "operDay": "operation_rule",
    "weekdayOperOpenHhmm": "weekday_start",
    "weekdayOperColseHhmm": "weekday_end",
    "satOperOperOpenHhmm": "weekend_start",
    "satOperCloseHhmm": "weekend_end",
    "holidayOperOpenHhmm": "holiday_start",
    "holidayCloseOpenHhmm": "holiday_end",
    "parkingchrgeInfo": "pay_type",
    "basicTime": "base_time",
    "basicCharge": "base_fee",
    "addUnitTime": "add_time",
    "addUnitCharge": "add_fee",
    "dayCmmtkt": "day_max_fee",
    "monthCmmtkt": "monthly_fee",
    "metpay": "pay_method",
    "institutionNm": "operator",
    "phoneNumber": "phone",
    "latitude": "latitude",
    "longitude": "longitude",
}

INT_COLUMNS = [
    "capacity", "base_time", "base_fee", "add_time", "add_fee",
    "day_max_fee", "monthly_fee",
    "weekday_start", "weekday_end", "weekend_start", "weekend_end",
    "holiday_start", "holiday_end",
]
TIME_COLUMNS = [
    "weekday_start", "weekday_end", "weekend_start", "weekend_end",
    "holiday_start", "holiday_end",
]


# ---------------------------------------------------------------------------
# 1) 원본 읽기 (CSV / API)
# ---------------------------------------------------------------------------
def find_raw_file() -> Path | None:
    for path in RAW_CANDIDATES:
        if path.exists():
            return path
    return None


def load_csv(path: str | Path | None = None) -> pd.DataFrame:
    """표준데이터 CSV를 인코딩 자동 판별로 읽는다 (한글 헤더 그대로)."""
    path = Path(path) if path else find_raw_file()
    if path is None:
        raise FileNotFoundError(
            "전국주차장정보표준데이터 CSV가 없습니다.\n"
            "  https://www.data.go.kr/data/15012896/standard.do 에서 내려받아\n"
            f"  {RAW_CANDIDATES[0]} 로 저장해주세요."
        )

    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            df = pd.read_csv(path, encoding=encoding, low_memory=False)
        except (UnicodeDecodeError, LookupError) as exc:
            last_error = exc
            continue
        if "주차장명" in df.columns:
            return df
        last_error = ValueError(f"{encoding}로 읽었으나 '주차장명' 컬럼이 없음")

    raise ValueError(f"{path} 를 읽지 못했습니다: {last_error}")


def fetch_api(service_key: str | None = None, max_pages: int = 30, timeout: int = 20) -> pd.DataFrame:
    """공공데이터포털 오픈 API로 표준데이터를 받아온다 (영문 키 응답).

    전국 데이터라 15만 건이 넘는다. max_pages로 상한을 둔다
    (1000건 × 30페이지 = 3만 건). 자치구 단위로만 쓸 거라면 CSV 쪽이 훨씬 빠르다.
    """
    service_key = service_key or config.DATA_GO_KR_API_KEY
    if not service_key:
        raise RuntimeError(".env 에 DATA_GO_KR_API_KEY 가 없습니다.")

    rows: list[dict] = []
    for page in range(1, max_pages + 1):
        params = {
            "serviceKey": service_key,
            "pageNo": page,
            "numOfRows": API_PAGE_SIZE,
            "type": "json",
        }
        try:
            payload = requests.get(API_URL, params=params, timeout=timeout).json()
        except (requests.RequestException, ValueError) as exc:
            raise RuntimeError(f"표준데이터 API 호출 실패: {exc}") from exc

        body = payload.get("response", {}).get("body", {})
        header = payload.get("response", {}).get("header", {})
        if header.get("resultCode") not in (None, "00"):
            raise RuntimeError(f"표준데이터 API 오류: {header.get('resultMsg')}")

        items = body.get("items") or []
        if isinstance(items, dict):  # 결과가 1건이면 dict로 오는 경우가 있다
            items = [items]
        rows.extend(items)

        if len(rows) >= int(body.get("totalCount", len(rows))) or not items:
            break

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 2) 필터 · 스키마 변환
# ---------------------------------------------------------------------------
def filter_district(df: pd.DataFrame, keyword: str) -> pd.DataFrame:
    """지번주소 또는 도로명주소에 자치구명이 포함된 행만 남긴다."""
    address_cols = [c for c in ("소재지지번주소", "소재지도로명주소", "lnmadr", "rdnmadr")
                    if c in df.columns]
    if not address_cols:
        return df.copy()

    mask = pd.Series(False, index=df.index)
    for col in address_cols:
        mask |= df[col].astype(str).str.contains(keyword, na=False)
    return df.loc[mask].copy()


def _hhmm(series: pd.Series) -> pd.Series:
    """'09:00' / '0900' / 900 처럼 섞여 오는 시각 표기를 HHMM 정수로 통일."""
    text = series.astype(str).str.strip().str.replace(":", "", regex=False)
    return pd.to_numeric(text, errors="coerce").round().astype("Int64")


def to_table_schema(df: pd.DataFrame) -> pd.DataFrame:
    """CSV/API 어느 쪽 원본이든 공영 수집기와 같은 스키마로 변환."""
    column_map = CSV_COLUMN_MAP if "주차장명" in df.columns else API_COLUMN_MAP
    out = df.rename(columns=column_map)
    out = out[[c for c in dict.fromkeys(column_map.values()) if c in out.columns]].copy()

    for col in ("latitude", "longitude"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").replace(0.0, pd.NA)

    for col in TIME_COLUMNS:
        if col in out.columns:
            out[col] = _hhmm(out[col])

    for col in INT_COLUMNS:
        if col in out.columns and col not in TIME_COLUMNS:
            out[col] = pd.to_numeric(out[col], errors="coerce").round().astype("Int64")

    # 지번주소가 비어 있으면 도로명주소로 채운다 (자치구 추출·검색에 둘 다 쓰인다)
    if "road_address" in out.columns:
        if "address" not in out.columns:
            out["address"] = pd.NA
        out["address"] = out["address"].replace("", pd.NA).fillna(out["road_address"])

    out["parking_id"] = "STD-" + out["parking_id"].astype(str).str.strip()
    out["parking_name"] = out["parking_name"].astype(str).str.strip()
    out["district"] = out["address"].astype(str).str.extract(
        r"(?:^|\s)([가-힣]+구)(?=\s|$)", expand=False
    )

    # '공영'/'민영' 외의 표기(공백, '민영주차장' 등)를 정리
    if "lot_category" in out.columns:
        out["lot_category"] = (
            out["lot_category"].astype(str).str.strip()
            .str.replace("주차장", "", regex=False)
            .replace({"": "민영", "nan": "민영"})
        )
    else:
        out["lot_category"] = "민영"

    # 부설주차장은 유형이 '부설'로 오는데, 이용자 입장에서는 민영과 같은 취급이라
    # lot_category 는 그대로 두고 lot_type 에만 남긴다.
    if "lot_type" in out.columns:
        out["lot_type"] = out["lot_type"].astype(str).str.strip().str.replace("주차장", "", regex=False)

    out["source"] = "standard"
    return out.reset_index(drop=True)


def collect(district: str | None = None, use_api: bool = False) -> pd.DataFrame:
    """원본 읽기 -> (자치구 필터) -> 스키마 변환까지 한 번에."""
    raw = fetch_api() if use_api else load_csv()
    if district:
        raw = filter_district(raw, district)
    return to_table_schema(raw)


def main() -> None:
    parser = argparse.ArgumentParser(description="전국주차장정보표준데이터 정제 (민영·부설)")
    parser.add_argument("--district", help="자치구명 필터 (예: 종로구)")
    parser.add_argument("--api", action="store_true", help="CSV 대신 오픈 API로 수집")
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT), help="저장 경로")
    args = parser.parse_args()

    result = collect(district=args.district, use_api=args.api)
    print(f"수집: {len(result):,}곳")
    if not result.empty:
        print(result["lot_category"].value_counts().to_string())

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"저장 완료 -> {out_path}")


if __name__ == "__main__":
    main()
