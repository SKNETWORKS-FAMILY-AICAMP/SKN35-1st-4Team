"""
[담당: 승희] 주차 기록 (PARKING_LOG 테이블).

"내 차 어디에 뒀더라" 를 해결하는 기능이다.
주차장 검색 결과에서 고르거나, 노상처럼 주차장이 아닌 곳이면 주소를 직접 적는다.

parking_name 을 따로 저장하는 이유
    parking_id 만 두고 PARKING_LOG -> PARKING_LOT 조인으로 이름을 가져오면 깔끔하지만,
    지금 주차장 목록은 DB가 아니라 CSV에서 올 수도 있어서 조인이 항상 되지는 않는다.
    그래서 기록할 때 이름을 같이 박아둔다 (비정규화). 주차장 정보가 나중에 바뀌어도
    "그때 내가 세운 곳"의 이름은 그대로 남는 장점도 있다.

저장소는 common/auth.py 와 같다 (MySQL 또는 data/app.db).
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
from sqlalchemy import text

from common.auth import ensure_tables, get_engine


def add_log(
    user_id: int,
    address: str,
    parked_at: datetime,
    is_charged: bool = False,
    parking_id: str | None = None,
    parking_name: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    memo: str | None = None,
) -> None:
    """주차 기록 한 건 저장."""
    ensure_tables()
    with get_engine().begin() as conn:
        conn.execute(
            text(
                "INSERT INTO PARKING_LOG "
                "(user_id, parking_id, parking_name, address, latitude, longitude, "
                " parked_at, is_charged, memo) "
                "VALUES (:user_id, :parking_id, :parking_name, :address, :lat, :lng, "
                "        :parked_at, :is_charged, :memo)"
            ),
            {
                "user_id": user_id,
                "parking_id": parking_id,
                "parking_name": parking_name,
                "address": address,
                "lat": latitude,
                "lng": longitude,
                "parked_at": parked_at,
                "is_charged": bool(is_charged),
                "memo": memo or None,
            },
        )


def list_logs(user_id: int, limit: int = 300) -> pd.DataFrame:
    """내 주차 기록을 최근 순으로."""
    ensure_tables()
    with get_engine().connect() as conn:
        df = pd.read_sql(
            text(
                "SELECT log_id, parking_id, parking_name, address, latitude, longitude, "
                "       parked_at, is_charged, memo "
                "FROM PARKING_LOG WHERE user_id = :user_id "
                "ORDER BY parked_at DESC LIMIT :limit"
            ),
            conn,
            params={"user_id": user_id, "limit": limit},
        )

    if df.empty:
        return df

    # SQLite는 날짜를 문자열로 돌려주므로 여기서 통일한다
    df["parked_at"] = pd.to_datetime(df["parked_at"], errors="coerce")
    df["is_charged"] = df["is_charged"].astype(bool)
    # 주차장을 고르지 않고 주소만 적은 기록은 이름 칸이 비어있다
    df["place"] = df["parking_name"].fillna(df["address"])
    return df


def delete_log(user_id: int, log_id: int) -> None:
    """내 기록만 지울 수 있게 user_id를 조건에 함께 넣는다."""
    ensure_tables()
    with get_engine().begin() as conn:
        conn.execute(
            text("DELETE FROM PARKING_LOG WHERE log_id = :log_id AND user_id = :user_id"),
            {"log_id": log_id, "user_id": user_id},
        )


def summary(logs: pd.DataFrame, now: datetime | None = None) -> dict:
    """기록 요약: 총 횟수, 이번 달 횟수, 유료 비율, 가장 자주 간 곳."""
    if logs.empty:
        return {"total": 0, "this_month": 0, "paid_ratio": 0.0, "favorite": "-"}

    now = now or datetime.now()
    same_month = (logs["parked_at"].dt.year == now.year) & (
        logs["parked_at"].dt.month == now.month
    )
    return {
        "total": len(logs),
        "this_month": int(same_month.sum()),
        "paid_ratio": float(logs["is_charged"].mean()),
        "favorite": logs["place"].mode().iloc[0] if not logs["place"].mode().empty else "-",
    }
