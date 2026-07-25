"""
로컬 MySQL 공통 연결/쿼리 모듈 (DBeaver로 만든 DB에 접속).

사용 예
    from common.db import read_sql

    # 바인드 파라미터는 SQLAlchemy text() 스타일(:name)을 사용한다.
    df = read_sql(
        "SELECT * FROM PUBLIC_PARKING_LOT WHERE address LIKE :addr",
        {"addr": "%종로구%"},
    )

나중에 TiDB Cloud로 옮길 때는 .env의 MYSQL_* 값을 TiDB 접속 정보로 바꾸고,
아래 create_engine에 connect_args={"ssl": {"ssl": {}}} 만 추가하면 된다
(TiDB Cloud Serverless는 SSL 필수).
"""

from functools import lru_cache

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

import config


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """SQLAlchemy engine을 한 번만 생성해서 재사용한다 (연결 재사용/캐싱)."""
    if not config.is_db_configured():
        raise RuntimeError(
            ".env에 MYSQL_HOST/MYSQL_USER/MYSQL_DATABASE를 먼저 채워주세요."
        )

    url = (
        f"mysql+pymysql://{config.MYSQL_USER}:{config.MYSQL_PASSWORD}"
        f"@{config.MYSQL_HOST}:{config.MYSQL_PORT}/{config.MYSQL_DATABASE}"
        "?charset=utf8mb4"
    )
    return create_engine(url)


def read_sql(sql: str, params: dict | None = None) -> pd.DataFrame:
    """SELECT 쿼리를 실행하고 DataFrame으로 반환."""
    with get_engine().connect() as conn:
        return pd.read_sql(text(sql), conn, params=params)


def execute(sql: str, params: dict | None = None) -> None:
    """INSERT/UPDATE/DELETE 등 결과를 반환하지 않는 쿼리 실행."""
    with get_engine().begin() as conn:
        conn.execute(text(sql), params or {})