"""
[담당: 승희] 주차장 검색 페이지가 쓰는 데이터 로더.

주차장 목록을 아래 순서로 찾는다. DB가 없어도 앱이 돌아간다.

    1) MySQL PARKING_LOT
    2) data/cleaned/parking_lot.csv
    3) 둘 다 없으면 DISTRICTS를 즉석 수집 (네트워크 필요)

실시간 여유는 따로 받아서 붙인다 (목록은 30분, 여유는 60초 캐시).
공영/민영 구분은 테이블이 아니라 lot_category 컬럼이다 (db/schema.sql 참고).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # 직접 실행 지원

import config  # noqa: E402
from collectors import seoul_parking  # noqa: E402

PARKING_CSV = Path(__file__).resolve().parent.parent / "data/cleaned/parking_lot.csv"
PARKING_TABLE = "PARKING_LOT"

# CSV도 DB도 없을 때 즉석 수집할 자치구.
# 범위를 넓히려면 collectors/seoul_parking.py --district all 로 CSV를 다시 만든다.
DISTRICTS = ["종로구"]


def _from_db() -> pd.DataFrame | None:
    """DB에서 읽는다. DB 설정이 아예 없으면 None(=CSV로 폴백).

    설정이 있는데 실패하면 예외를 올린다. 조용히 CSV로 넘어가면 화면은
    멀쩡한데 실제로는 옛 CSV를 보고 있게 되어, 적재 누락이나 접속 끊김을
    눈치챌 수 없다. 비어 있는 결과도 그대로 돌려준다(적재 안 된 상태를 감추지 않는다).
    """
    if not config.is_db_configured():
        return None

    from common.db import DataSourceError, read_sql

    try:
        return read_sql(f"SELECT * FROM {PARKING_TABLE}")  # noqa: S608 - 코드 상수
    except Exception as exc:  # noqa: BLE001 - 원인 무관하게 사용자에게 알린다
        raise DataSourceError(
            f"DB에서 주차장 목록을 읽지 못했습니다 ({type(exc).__name__}). "
            "테이블이 비었으면 `uv run python loaders/load_all.py`, "
            "접속이 문제면 .env의 DB_* 값을 확인하세요."
        ) from exc


@st.cache_data(ttl=1800, show_spinner="주차장 데이터를 불러오는 중…")
def load_lots() -> tuple[pd.DataFrame, str]:
    """주차장 목록 + 어디서 읽었는지 설명 한 줄."""
    lots = _from_db()
    note = f"DB {PARKING_TABLE}"

    # DB에서 읽었으면 CSV는 쳐다보지 않는다. 아래 폴백은 .env에 DB 설정이
    # 아예 없는 로컬 개발용이다 (DB가 있는데 실패하면 _from_db가 예외를 올린다).
    if lots is None and PARKING_CSV.exists():
        lots = pd.read_csv(PARKING_CSV, encoding="utf-8-sig")
        note = PARKING_CSV.name

    if lots is None:
        lots = seoul_parking.collect(DISTRICTS)
        note = f"즉석 수집 ({', '.join(DISTRICTS)})"

    # 검색·표시에 꼭 필요한 값만 보정
    lots["district"] = lots["district"].fillna("기타")
    lots["address"] = lots["address"].fillna("주소 미상")
    for col in ("latitude", "longitude"):
        lots[col] = pd.to_numeric(lots[col], errors="coerce")

    return lots, f"주차장 목록: {note} ({len(lots):,}곳)"


@st.cache_data(ttl=60, show_spinner=False)
def load_realtime() -> pd.DataFrame:
    return seoul_parking.fetch_realtime()


def load_parking_lots() -> tuple[pd.DataFrame, list[str]]:
    """페이지에서 쓰는 최종 테이블 + 출처 설명 목록."""
    lots, note = load_lots()
    merged = seoul_parking.attach_realtime(lots, load_realtime())

    live = int(merged["available"].notna().sum())
    notes = [
        note,
        f"실시간 여유: {live:,}곳 (서울시 OA-21709)" if live
        else "실시간 여유: 없음 (.env의 SEOUL_OPENAPI_KEY 확인)",
    ]
    return merged, notes
