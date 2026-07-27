"""
정제 CSV -> MySQL 적재 공통 스크립트.

사용법
    # 주차장·CCTV·단속이력 세 개를 한 번에 (보통 이걸 쓴다)
    uv run python loaders/load_all.py

    # 테이블 하나만 골라서
    uv run python loaders/load_to_db.py --csv data/cleaned/parking_lot.csv \
        --table PARKING_LOT --if-exists truncate

    # 적재 후 확인
    uv run python loaders/check_db.py

접속 대상은 .env(또는 st.secrets)의 DB_* 값을 따른다. 로컬 MySQL이든
TiDB Cloud든 코드는 그대로고 접속 정보만 바꾸면 된다.

주차장 CSV는 `uv run python collectors/seoul_parking.py` 로 만든다.
단속 이력 CSV는 용량이 커서 git에 올리지 않으므로(.gitignore),
배포판은 여기서 적재한 DB만 바라본다.

PARKING_LOT 을 적재할 때는 표시용 컬럼(fee, operation_time)을 자동으로 만들어 넣고,
스키마에 없는 컬럼은 버린다. 그 외 테이블은 CSV 컬럼을 그대로 넣는다.

--if-exists 옵션
    append   : 기존 행 유지하고 추가 (기본값)
    replace  : 테이블을 지우고 새로 만듦 (스키마가 pandas 추론값으로 바뀌니 주의)
    truncate : 테이블 구조는 두고 데이터만 비우고 다시 넣기  <- 재적재는 보통 이게 맞다
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collectors.seoul_parking import COLUMNS  # noqa: E402
from common.db import execute, get_engine  # noqa: E402
from common.recommend import format_fee, format_hours  # noqa: E402

PARKING_TABLE = "PARKING_LOT"
ENFORCEMENT_TABLE = "ENFORCEMENT_HISTORY"
CCTV_TABLE = "CCTV_INFO"
FAQ_TABLE = "FAQ"
FAQ2_TABLE = "FAQ2"

# db/schema.sql 기준
ENFORCEMENT_COLUMNS = ["address", "enforced_at", "latitude", "longitude"]
CCTV_COLUMNS = ["address", "latitude", "longitude", "organization", "purpose"]
# faq_id 는 AUTO_INCREMENT 라 넣지 않는다
FAQ_COLUMNS = ["category", "question", "answer", "source"]
# 민원 게시판. faq2_id 는 원본 CSV 값이 그대로 INT 라 살려서 넣는다
FAQ2_COLUMNS = [
    "faq2_id", "q_title", "q_writer", "q_date",
    "question", "a_depart", "a_date", "answer", "source",
]
FAQ2_DATE_COLUMNS = ["q_date", "a_date"]

# 23만 건을 한 번에 INSERT 하면 패킷 한도에 걸린다
CHUNK = 5_000

# db/schema.sql 의 PARKING_LOT 컬럼 = 수집 컬럼 + 표시용 2개
PARKING_COLUMNS = [*COLUMNS, "fee", "operation_time"]


def prepare_parking(df: pd.DataFrame) -> pd.DataFrame:
    """PARKING_LOT 스키마에 맞춰 컬럼을 정리하고 표시용 문구를 채운다."""
    out = df.copy()
    out["fee"] = out.apply(format_fee, axis=1)
    out["operation_time"] = out.apply(format_hours, axis=1)

    for col in PARKING_COLUMNS:
        if col not in out.columns:
            out[col] = None

    out = out[PARKING_COLUMNS]
    # 문자열 컬럼의 결측을 None으로 (숫자형 NaN/NA는 to_sql이 알아서 NULL로 넣는다)
    return out.where(pd.notna(out), None)


def prepare_enforcement(df: pd.DataFrame) -> pd.DataFrame:
    """단속 이력 CSV -> ENFORCEMENT_HISTORY 스키마.

    원본이 '단속일/단속시간/구주소/위도/경도'로 오는 경우가 있어
    common/risk_data.py 의 정규화 로직을 그대로 재사용한다.
    """
    from common.risk_data import ENFORCEMENT_COLUMN_MAP

    out = df.copy()
    if {"단속일", "단속시간"} <= set(out.columns):
        day = pd.to_numeric(out["단속일"], errors="coerce")
        out = out[day.notna()].copy()
        out["단속일시"] = day[day.notna()].astype("int64").astype(str) + " " + out["단속시간"].astype(str)
    out = out.rename(columns=ENFORCEMENT_COLUMN_MAP)

    out["enforced_at"] = pd.to_datetime(out.get("enforced_at"), errors="coerce")
    for col in ("latitude", "longitude"):
        out[col] = pd.to_numeric(out.get(col), errors="coerce")

    out = out.dropna(subset=["address"])
    return out[ENFORCEMENT_COLUMNS].where(pd.notna(out[ENFORCEMENT_COLUMNS]), None)


def prepare_cctv(df: pd.DataFrame) -> pd.DataFrame:
    """CCTV 정제본 -> CCTV_INFO 스키마."""
    out = df.copy()
    for col in CCTV_COLUMNS:
        if col not in out.columns:
            out[col] = None
    for col in ("latitude", "longitude"):
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=["address", "latitude", "longitude"])
    return out[CCTV_COLUMNS]


def prepare_faq(df: pd.DataFrame) -> pd.DataFrame:
    """FAQ 정제본 -> FAQ 스키마.

    CSV의 faq_id는 'FAQ_001' 같은 문자열인데 테이블 faq_id는 INT AUTO_INCREMENT라
    그대로 넣을 수 없다. 어차피 화면에서 쓰지 않는 값이라 버리고 DB가 번호를 매기게 둔다.
    출처 컬럼명도 CSV(source_org)와 스키마(source)가 달라 맞춰준다.
    """
    out = df.rename(columns={"source_org": "source"}).copy()
    for col in FAQ_COLUMNS:
        if col not in out.columns:
            out[col] = None

    # question/answer 는 NOT NULL 이라 빈 행은 미리 걸러낸다
    out = out.dropna(subset=["question", "answer"])
    return out[FAQ_COLUMNS]


def prepare_faq2(df: pd.DataFrame) -> pd.DataFrame:
    """민원 게시판 정제본 -> FAQ2 스키마.

    q_date/a_date 는 CSV에서 문자열로 읽히는데 컬럼 타입은 DATETIME 이라
    미리 파싱해서 넣는다. 파싱 실패한 행은 NOT NULL 제약에 걸리므로 버린다.
    """
    out = df.copy()
    for col in FAQ2_COLUMNS:
        if col not in out.columns:
            out[col] = None

    for col in FAQ2_DATE_COLUMNS:
        out[col] = pd.to_datetime(out[col], errors="coerce")

    required = [c for c in FAQ2_COLUMNS if c != "source"]
    before = len(out)
    out = out.dropna(subset=required)
    if len(out) < before:
        print(f"  NOT NULL 위반 {before - len(out)}행 제외")

    return out[FAQ2_COLUMNS]


PREPARE = {
    PARKING_TABLE: prepare_parking,
    ENFORCEMENT_TABLE: prepare_enforcement,
    CCTV_TABLE: prepare_cctv,
    FAQ_TABLE: prepare_faq,
    FAQ2_TABLE: prepare_faq2,
}


def load_csv(csv_path: str | Path, table: str, if_exists: str = "append") -> int:
    """CSV 한 개를 테이블 하나에 적재하고 넣은 행 수를 돌려준다.

    loaders/load_all.py 에서도 이 함수를 그대로 재사용한다.
    """
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    print(f"읽음: {csv_path} ({len(df):,}행 × {len(df.columns)}컬럼)")

    key = table.upper()
    if key in PREPARE:
        df = PREPARE[key](df)
        print(f"{key} 스키마로 정리: {len(df):,}행 × {len(df.columns)}컬럼")

    if if_exists == "truncate":
        execute(f"TRUNCATE TABLE {table}")  # noqa: S608 - 코드/CLI로 지정한 테이블명
        print(f"{table} 비움")
        mode = "append"
    else:
        mode = if_exists

    df.to_sql(
        table, get_engine(), if_exists=mode, index=False,
        chunksize=CHUNK, method="multi",
    )
    print(f"적재 완료 -> {table} ({len(df):,}행, mode={if_exists})")
    return len(df)


def main() -> None:
    parser = argparse.ArgumentParser(description="정제 CSV를 MySQL 테이블에 적재")
    parser.add_argument("--csv", required=True, help="적재할 CSV 경로")
    parser.add_argument("--table", required=True, help="대상 테이블명")
    parser.add_argument(
        "--if-exists",
        default="append",
        choices=["append", "replace", "truncate"],
        help="기존 데이터 처리 방식 (기본: append)",
    )
    args = parser.parse_args()
    load_csv(args.csv, args.table, args.if_exists)


if __name__ == "__main__":
    main()
