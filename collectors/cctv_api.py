## ============================================================
## 서울시 열린데이터광장 - 종로구 불법주정차 단속 CCTV 위치정보 수집.

## 사용 예
##    uv run python collectors/cctv_api.py

## 수집한 데이터는 CCTV_INFO 테이블에 저장하고,
## 원본 백업은 data/raw/cctv_raw.csv 로 저장한다.
## ============================================================

from pathlib import Path

import pandas as pd
import requests

import config
from common.db import get_engine

API_BASE = "http://openapi.seoul.go.kr:8088"
SERVICE = "TbOpendataFixedcctvJN"
PAGE_SIZE = 1000

RAW_PATH = Path("data/raw/cctv_raw.csv")
CLEANED_PATH = Path("data/cleaned/cctv_cleaned.csv")


def fetch_all_cctv() -> pd.DataFrame:
    """서울시 API에서 CCTV 데이터를 페이지네이션으로 전량 가져온다."""
    if not config.SEOUL_OPENAPI_KEY:
        raise RuntimeError(".env에 SEOUL_OPENAPI_KEY를 먼저 채워주세요.")

    check_url = f"{API_BASE}/{config.SEOUL_OPENAPI_KEY}/json/{SERVICE}/1/1"
    resp = requests.get(check_url, timeout=10).json()
    result = resp[SERVICE]["RESULT"]
    if result["CODE"] != "INFO-000":
        raise RuntimeError(f"API 에러: {result['MESSAGE']}")

    total = resp[SERVICE]["list_total_count"]
    print(f"전체 건수: {total}")

    all_rows = []
    for start in range(1, total + 1, PAGE_SIZE):
        end = min(start + PAGE_SIZE - 1, total)
        url = f"{API_BASE}/{config.SEOUL_OPENAPI_KEY}/json/{SERVICE}/{start}/{end}"
        r = requests.get(url, timeout=10).json()
        result = r[SERVICE]["RESULT"]
        if result["CODE"] != "INFO-000":
            print(f"경고: {start}~{end} 구간 에러 - {result['MESSAGE']}")
            continue
        all_rows.extend(r[SERVICE]["row"])
        print(f"{start}~{end} 가져오기 완료 (누적 {len(all_rows)}건)")

    return pd.DataFrame(all_rows)


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """API 원본 컬럼명을 CCTV_INFO 테이블 스키마에 맞게 정리한다."""
    df_clean = df.rename(columns={
        "FIX_CCTV_ADDR": "address",
        "LAT": "latitude",
        "LOT": "longitude",
        "CGG_CD": "organization",
        "GRNDS_SE": "purpose",
    })[["address", "latitude", "longitude", "organization", "purpose"]]

    df_clean["latitude"] = pd.to_numeric(df_clean["latitude"], errors="coerce")
    df_clean["longitude"] = pd.to_numeric(df_clean["longitude"], errors="coerce")

    before = len(df_clean)
    df_clean = df_clean.dropna(subset=["latitude", "longitude"])
    dropped = before - len(df_clean)
    if dropped:
        print(f"좌표 누락으로 {dropped}건 제외")

    return df_clean.reset_index(drop=True)


def save_to_db(df: pd.DataFrame) -> None:
    """CCTV_INFO 테이블에 저장한다. (기존 데이터는 유지하고 append)"""
    engine = get_engine()
    df.to_sql("CCTV_INFO", con=engine, if_exists="append", index=False)
    print(f"DB 적재 완료: {len(df)}건")


def main():
    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    CLEANED_PATH.parent.mkdir(parents=True, exist_ok=True)

    df_raw = fetch_all_cctv()
    df_raw.to_csv(RAW_PATH, index=False, encoding="utf-8-sig")
    print(f"원본 저장: {RAW_PATH}")

    df_clean = clean(df_raw)
    df_clean.to_csv(CLEANED_PATH, index=False, encoding="utf-8-sig")
    print(f"정제본 저장: {CLEANED_PATH}")

    save_to_db(df_clean)


if __name__ == "__main__":
    main()