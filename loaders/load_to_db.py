"""
정제 CSV -> MySQL 적재 공통 스크립트.

사용법
    uv run python loaders/load_to_db.py --csv data/cleaned/public_parking.csv \
        --table PUBLIC_PARKING_LOT --if-exists append

주차장 테이블(PUBLIC_PARKING_LOT / PRIVATE_PARKING_LOT)을 적재할 때는
표시용 컬럼(fee, operation_time)을 자동으로 만들어 넣고, 스키마에 없는 컬럼은 버린다.
그 외 테이블은 CSV 컬럼을 그대로 넣는다.

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

from common.db import execute, get_engine  # noqa: E402
from common.recommend import format_fee, format_hours  # noqa: E402

PARKING_TABLES = {"PUBLIC_PARKING_LOT", "PRIVATE_PARKING_LOT"}

# db/schema.sql 의 주차장 테이블 컬럼 (이 순서/이름만 적재한다)
PARKING_COLUMNS = [
    "parking_id", "parking_name", "lot_category", "lot_type", "operation_rule",
    "district", "address", "latitude", "longitude", "phone", "capacity",
    "pay_type", "base_fee", "base_time", "add_fee", "add_time",
    "day_max_fee", "monthly_fee",
    "weekday_start", "weekday_end", "weekend_start", "weekend_end",
    "holiday_start", "holiday_end", "source", "fee", "operation_time",
]


def prepare_parking(df: pd.DataFrame) -> pd.DataFrame:
    """주차장 테이블 스키마에 맞춰 컬럼을 정리하고 표시용 문구를 채운다."""
    out = df.copy()
    out["fee"] = out.apply(format_fee, axis=1)
    out["operation_time"] = out.apply(format_hours, axis=1)

    for col in PARKING_COLUMNS:
        if col not in out.columns:
            out[col] = None

    out = out[PARKING_COLUMNS]
    # 문자열 컬럼의 결측을 None으로 (숫자형 NaN/NA는 to_sql이 알아서 NULL로 넣는다)
    return out.where(pd.notna(out), None)


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

    df = pd.read_csv(args.csv, encoding="utf-8-sig")
    print(f"읽음: {args.csv} ({len(df):,}행 × {len(df.columns)}컬럼)")

    if args.table.upper() in PARKING_TABLES:
        df = prepare_parking(df)
        print(f"주차장 스키마로 정리: {len(df.columns)}컬럼")

    if args.if_exists == "truncate":
        execute(f"TRUNCATE TABLE {args.table}")  # noqa: S608 - 사용자가 지정한 테이블명
        print(f"{args.table} 비움")
        if_exists = "append"
    else:
        if_exists = args.if_exists

    df.to_sql(args.table, get_engine(), if_exists=if_exists, index=False)
    print(f"적재 완료 -> {args.table} ({len(df):,}행, mode={args.if_exists})")


if __name__ == "__main__":
    main()
