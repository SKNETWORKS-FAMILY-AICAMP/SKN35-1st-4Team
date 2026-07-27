"""
DB 연결 진단 스크립트.

    uv run python loaders/check_db.py

접속이 되는지, 스키마의 테이블이 다 있는지, 각 테이블에 몇 행이 들어있는지
한 번에 보여준다. TiDB Cloud로 옮긴 뒤 "왜 화면이 비지?" 를 빠르게 가르는 용도.

비밀번호 등은 .env / st.secrets 에서 읽고 화면에 찍지 않는다.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import inspect, text  # noqa: E402

import config  # noqa: E402

# db/schema.sql 에 정의된 테이블
EXPECTED = [
    "PARKING_LOT",
    "ENFORCEMENT_HISTORY",
    "CCTV_INFO",
    "FAQ",
    "COMPLAIN",  # 민원 게시판 (예전 이름 FAQ2)
    "USERS",
    "PARKING_LOG",
]

# CSV로 적재하는 게 아니라 사용자가 앱에서 만드는 테이블.
# 비어 있어도 "적재하세요" 라고 안내하면 안 된다.
USER_GENERATED = {"USERS", "PARKING_LOG"}


def main() -> None:
    print("접속 정보")
    print(f"  host     : {config.MYSQL_HOST}:{config.MYSQL_PORT}")
    print(f"  user     : {config.MYSQL_USER}")
    print(f"  database : {config.MYSQL_DATABASE}")

    if not config.MYSQL_PASSWORD or config.MYSQL_PASSWORD.startswith("<"):
        print("\n✗ .env 의 DB_PASSWORD 가 비어 있습니다.")
        raise SystemExit(1)

    if config.MYSQL_DATABASE in ("sys", "test", ""):
        print(f"\n⚠ database 가 '{config.MYSQL_DATABASE}' 입니다. "
              "스키마를 만든 DB(parking_project)가 맞는지 확인하세요.")

    from common.db import get_engine

    try:
        engine = get_engine()
        with engine.connect() as conn:
            version = conn.execute(text("SELECT VERSION()")).scalar()
    except Exception as exc:  # noqa: BLE001
        print(f"\n✗ 접속 실패\n  {type(exc).__name__}: {str(exc)[:300]}")
        raise SystemExit(1) from exc

    print(f"\n✓ 접속 성공 (server {version})")

    existing = {name.upper() for name in inspect(engine).get_table_names()}
    print("\n테이블 상태")
    with engine.connect() as conn:
        for table in EXPECTED:
            if table not in existing:
                print(f"  ✗ {table:22s} 없음 — db/schema.sql 을 실행하세요")
                continue
            rows = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()  # noqa: S608
            mark = "○" if rows == 0 else "✓"
            note = ""
            if rows == 0:
                note = (
                    "  (비어 있음 — 앱에서 가입/등록하면 쌓임)"
                    if table in USER_GENERATED
                    else "  (비어 있음 — loaders/load_all.py 로 적재)"
                )
            print(f"  {mark} {table:22s} {rows:>9,}행{note}")

    extra = existing - set(EXPECTED)
    if extra:
        print(f"\n  그 외 테이블: {', '.join(sorted(extra))}")


if __name__ == "__main__":
    main()
