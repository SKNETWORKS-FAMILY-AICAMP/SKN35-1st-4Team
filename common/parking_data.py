"""
[담당: 승희] 주차장 검색 페이지가 쓰는 데이터 로더.

DB가 아직 없어도 앱이 돌아가야 하므로, 아래 순서로 데이터를 찾는다.

    사이트 1) data/cleaned/site_parking.csv (주차정보안내시스템 수집 결과)  <- 주력 소스
           2) 없으면 SITE_DISTRICTS를 즉석 크롤링
    공영   1) MySQL PUBLIC_PARKING_LOT
           2) data/cleaned/public_parking.csv
           3) 저장소에 들어있는 원본 CSV(seoul_parking.csv)에서 즉석 정제
    민영   1) MySQL PRIVATE_PARKING_LOT
           2) data/cleaned/private_parking.csv
           3) data/raw/national_parking.csv (표준데이터) 즉석 정제
           4) 없으면 건너뜀 (사이트 데이터에 민영이 이미 들어있다)

주차정보안내시스템(parking.seoul.go.kr)이 주력인 이유
    공영 CSV는 좌표가 850곳 중 117곳뿐이라 지도가 거의 비었다. 사이트 수집분은
    좌표 100%에 민영·부설까지 포함한다(종로구 43곳 -> 232곳).
    공영 CSV는 주차장코드가 같아 자동으로 병합되며, 일 최대요금·정기권처럼
    사이트에 없는 값을 채워주는 보조 소스로 남긴다.

여유 정보(실시간 주차 대수)는 서울시 OA-21709 API에서 따로 받아 붙인다.
어느 단계에서 왔는지는 load_parking_lots()가 함께 돌려주는 note 목록으로 화면에 표시한다.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

import config
from collectors import (
    merge_parking,
    public_parking_api,
    realtime_parking_api,
    seoul_parking_crawler,
)
from collectors.merge_parking import TABLE_COLUMNS

ROOT = Path(__file__).resolve().parent.parent
PUBLIC_CSV = ROOT / "data/cleaned/public_parking.csv"
PRIVATE_CSV = ROOT / "data/cleaned/private_parking.csv"
SITE_CSV = ROOT / "data/cleaned/site_parking.csv"

# site_parking.csv가 없을 때 즉석으로 받아올 자치구.
# 범위를 넓히려면 collectors/seoul_parking_crawler.py --district all 로 CSV를 만들면 된다.
SITE_DISTRICTS = ["종로구"]

# DB에서 읽을 컬럼 (스키마에 없는 컬럼이 있어도 죽지 않도록 SELECT * 로 받는다)
PUBLIC_TABLE = "PUBLIC_PARKING_LOT"
PRIVATE_TABLE = "PRIVATE_PARKING_LOT"



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
    return pd.DataFrame(), "민영(표준데이터): 없음 - 주차정보안내시스템 수집분으로 대체"


def _site_from_crawl() -> pd.DataFrame | None:
    """CSV가 없으면 SITE_DISTRICTS를 즉석 수집 (원본 JSON 캐시가 있으면 그걸 쓴다)."""
    try:
        df = seoul_parking_crawler.collect(SITE_DISTRICTS)
    except (RuntimeError, OSError, ValueError):
        return None
    return df if not df.empty else None


def _load_site() -> tuple[pd.DataFrame, str]:
    df = _from_csv(SITE_CSV)
    if df is not None:
        return df, f"주차정보안내시스템: {SITE_CSV.name}"

    df = _site_from_crawl()
    if df is not None:
        return df, f"주차정보안내시스템: 즉석 수집 ({', '.join(SITE_DISTRICTS)})"

    return pd.DataFrame(), "주차정보안내시스템: 수집 실패"


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------
@st.cache_data(ttl=1800, show_spinner="주차장 데이터를 불러오는 중…")
def load_base_lots() -> tuple[pd.DataFrame, list[str]]:
    """사이트 + 공영 + 민영을 합쳐 중복 제거한 기본 테이블. (실시간 여유는 아직 없음)"""
    site, site_note = _load_site()
    public, public_note = _load_public()
    private, private_note = _load_private()

    # 순서가 곧 우선순위는 아니다 (merge_parking.SOURCE_PRIORITY가 대표 행을 정한다)
    merged = merge_parking.merge_sources(site, public, private)

    # 검색·표시에 꼭 필요한 값 보정
    if not merged.empty:
        merged["lot_category"] = merged["lot_category"].fillna("공영")
        merged["district"] = merged["district"].fillna("기타")
        merged["address"] = merged["address"].fillna("주소 미상")
        for col in ("latitude", "longitude"):
            merged[col] = pd.to_numeric(merged[col], errors="coerce")

    with_coord = int(merged[["latitude", "longitude"]].notna().all(axis=1).sum()) if not merged.empty else 0
    notes = [
        f"{site_note} ({len(site):,}곳)",
        f"{public_note} ({len(public):,}곳)",
        f"{private_note} ({len(private):,}곳)",
        f"중복 제거 후 {len(merged):,}곳 · 좌표 보유 {with_coord:,}곳",
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
