"""
[담당: 승희] 주차장 검색 페이지가 쓰는 데이터 로더.

DB가 아직 없어도 앱이 돌아가야 하므로, 아래 순서로 데이터를 찾는다.

    공영  1) MySQL PUBLIC_PARKING_LOT
          2) data/cleaned/public_parking.csv
          3) 저장소에 들어있는 원본 CSV(seoul_parking.csv)에서 즉석 정제  <- 항상 성공
    민영  1) MySQL PRIVATE_PARKING_LOT
          2) data/cleaned/private_parking.csv
          3) data/raw/national_parking.csv (표준데이터) 즉석 정제
          4) 없으면 샘플 4곳 (이름에 '(샘플)'을 붙여 실데이터와 구분)

여유 정보(실시간 주차 대수)는 서울시 OA-21709 API에서 따로 받아 붙인다.
어느 단계에서 왔는지는 load_parking_lots()가 함께 돌려주는 note 목록으로 화면에 표시한다.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

import config
from collectors import merge_parking, public_parking_api, realtime_parking_api
from collectors.merge_parking import TABLE_COLUMNS

ROOT = Path(__file__).resolve().parent.parent
PUBLIC_CSV = ROOT / "data/cleaned/public_parking.csv"
PRIVATE_CSV = ROOT / "data/cleaned/private_parking.csv"

# DB에서 읽을 컬럼 (스키마에 없는 컬럼이 있어도 죽지 않도록 SELECT * 로 받는다)
PUBLIC_TABLE = "PUBLIC_PARKING_LOT"
PRIVATE_TABLE = "PRIVATE_PARKING_LOT"

# 표준데이터 CSV를 아직 안 받았을 때 쓰는 민영주차장 샘플 (종로구)
SAMPLE_PRIVATE = pd.DataFrame([
    {"parking_id": "SAMPLE-1", "parking_name": "인사동 그랑서울 (샘플)", "lot_category": "민영",
     "lot_type": "부설", "district": "종로구", "address": "종로구 청진동 246",
     "latitude": 37.5717, "longitude": 126.9857, "capacity": 120,
     "base_fee": 1000, "base_time": 10, "add_fee": 500, "add_time": 10,
     "weekday_start": 0, "weekday_end": 2400, "weekend_start": 0, "weekend_end": 2400,
     "source": "sample"},
    {"parking_id": "SAMPLE-2", "parking_name": "광화문 D타워 (샘플)", "lot_category": "민영",
     "lot_type": "부설", "district": "종로구", "address": "종로구 청진동 24",
     "latitude": 37.5711, "longitude": 126.9780, "capacity": 300,
     "base_fee": 1200, "base_time": 15, "add_fee": 600, "add_time": 10,
     "weekday_start": 700, "weekday_end": 2200, "weekend_start": 900, "weekend_end": 2000,
     "source": "sample"},
    {"parking_id": "SAMPLE-3", "parking_name": "낙원상가 (샘플)", "lot_category": "민영",
     "lot_type": "노외", "district": "종로구", "address": "종로구 낙원동 284-6",
     "latitude": 37.5730, "longitude": 126.9880, "capacity": 80,
     "base_fee": 800, "base_time": 10, "add_fee": 400, "add_time": 10,
     "weekday_start": 600, "weekday_end": 2400, "weekend_start": 600, "weekend_end": 2400,
     "source": "sample"},
    {"parking_id": "SAMPLE-4", "parking_name": "동대문 밀리오레 (샘플)", "lot_category": "민영",
     "lot_type": "부설", "district": "중구", "address": "중구 을지로6가 18-185",
     "latitude": 37.5665, "longitude": 127.0075, "capacity": 200,
     "base_fee": 1000, "base_time": 30, "add_fee": 1000, "add_time": 30,
     "weekday_start": 0, "weekday_end": 2400, "weekend_start": 0, "weekend_end": 2400,
     "source": "sample"},
])


# ---------------------------------------------------------------------------
# 단계별 로더 - 각 함수는 실패하면 None을 돌려주고, 호출부가 다음 단계로 넘어간다
# ---------------------------------------------------------------------------
def _from_db(table: str) -> pd.DataFrame | None:
    if not config.is_db_configured():
        return None
    try:
        from common.db import read_sql

        df = read_sql(f"SELECT * FROM {table}")  # noqa: S608 - 테이블명은 코드 상수
    except Exception:  # noqa: BLE001 - DB 미적재/미기동 등 어떤 이유든 다음 단계로
        return None
    return df if not df.empty else None


def _from_csv(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
    except (OSError, ValueError):
        return None
    return df if not df.empty else None


def _public_from_raw() -> pd.DataFrame | None:
    """저장소에 들어있는 서울시 원본 CSV에서 즉석 정제 (최후의 보루)."""
    try:
        return public_parking_api.collect()
    except (FileNotFoundError, ValueError):
        return None


def _private_from_raw() -> pd.DataFrame | None:
    """표준데이터 CSV가 있으면 민영·부설만 즉석 정제."""
    try:
        from collectors import private_parking_crawler

        df = private_parking_crawler.collect()
    except (FileNotFoundError, RuntimeError, ValueError):
        return None
    return df if not df.empty else None


def _load_public() -> tuple[pd.DataFrame, str]:
    for loader, note in (
        (lambda: _from_db(PUBLIC_TABLE), f"공영: DB {PUBLIC_TABLE}"),
        (lambda: _from_csv(PUBLIC_CSV), f"공영: {PUBLIC_CSV.name}"),
        (_public_from_raw, "공영: 서울시 원본 CSV 즉석 정제"),
    ):
        df = loader()
        if df is not None:
            return df, note
    return pd.DataFrame(), "공영: 데이터 없음"


def _load_private() -> tuple[pd.DataFrame, str]:
    for loader, note in (
        (lambda: _from_db(PRIVATE_TABLE), f"민영: DB {PRIVATE_TABLE}"),
        (lambda: _from_csv(PRIVATE_CSV), f"민영: {PRIVATE_CSV.name}"),
        (_private_from_raw, "민영: 표준데이터 CSV 즉석 정제"),
    ):
        df = loader()
        if df is not None:
            return df, note
    return SAMPLE_PRIVATE.copy(), "민영: 샘플 4곳 (실데이터 미확보)"


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------
@st.cache_data(ttl=1800, show_spinner="주차장 데이터를 불러오는 중…")
def load_base_lots() -> tuple[pd.DataFrame, list[str]]:
    """공영 + 민영을 합쳐 중복 제거한 기본 테이블. (실시간 여유는 아직 없음)"""
    public, public_note = _load_public()
    private, private_note = _load_private()

    merged = merge_parking.merge_sources(public, private)

    # 검색·표시에 꼭 필요한 값 보정
    if not merged.empty:
        merged["lot_category"] = merged["lot_category"].fillna("공영")
        merged["district"] = merged["district"].fillna("기타")
        merged["address"] = merged["address"].fillna("주소 미상")
        for col in ("latitude", "longitude"):
            merged[col] = pd.to_numeric(merged[col], errors="coerce")

    notes = [
        f"{public_note} ({len(public):,}곳)",
        f"{private_note} ({len(private):,}곳)",
        f"중복 제거 후 {len(merged):,}곳",
    ]
    return merged, notes


@st.cache_data(ttl=60, show_spinner=False)
def load_realtime() -> pd.DataFrame:
    """실시간 주차 여유. 키가 없거나 API가 실패하면 빈 DataFrame."""
    try:
        return realtime_parking_api.fetch()
    except RuntimeError:
        return realtime_parking_api.empty_frame()


def load_parking_lots() -> tuple[pd.DataFrame, list[str]]:
    """페이지에서 쓰는 최종 테이블 + 데이터 출처 설명 목록."""
    base, notes = load_base_lots()
    if base.empty:
        return base, notes

    realtime = load_realtime()
    merged = realtime_parking_api.attach(base, realtime)

    live_count = int(merged["available"].notna().sum())
    if live_count:
        notes.append(f"실시간 여유 정보 {live_count:,}곳 (서울시 OA-21709)")
    else:
        notes.append("실시간 여유 정보 없음 (.env의 SEOUL_OPENAPI_KEY 확인)")
    return merged, notes


__all__ = ["TABLE_COLUMNS", "load_parking_lots", "load_base_lots", "load_realtime"]
