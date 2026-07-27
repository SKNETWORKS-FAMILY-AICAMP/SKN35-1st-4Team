"""
[담당: 승희] 주차장 추천 로직 + 표시용 텍스트 (순수 함수 모듈).

Streamlit/DB에 의존하지 않는 계산 전용 모듈이라 단독 테스트가 쉽다:
    uv run python common/recommend.py     # 자체 테스트 실행

추천 점수 = 거리 점수 × w1 + 여유 점수 × w2 + 요금 점수 × w3
각 점수는 0~1로 정규화되며, 가중치는 화면의 슬라이더로 사용자가 조절한다.

공영/민영 구분 없이 동일한 컬럼 규약(base_fee, add_fee, weekday_start ...)만 맞으면
그대로 동작한다. 컬럼 규약은 collectors/seoul_parking.py의 COLUMNS 참고.
"""

from datetime import datetime

import pandas as pd


# ---------------------------------------------------------------------------
# 1) 예상 주차요금 계산
# ---------------------------------------------------------------------------
def _to_float(value, default: float = 0.0) -> float:
    """결측값을 안전하게 실수로 변환.

    ⚠ 중요: DataFrame의 Int64(결측 허용 정수형) 컬럼에서 꺼낸 값은 None이 아니라
    pandas.NA 이고, `if value:` 로 판단하면 "boolean value of NA is ambiguous"
    TypeError가 난다. 반드시 pd.isna()로 먼저 걸러야 한다.
    """
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def estimate_fee(
    hours: float,
    base_fee: float | None,
    base_time: float | None,
    add_fee: float | None,
    add_time: float | None,
    day_max_fee: float | None = None,
) -> int:
    """N시간 주차 시 예상 요금(원)을 계산.

    서울시 공영주차장 요금 체계:
        기본요금(base_fee)으로 기본시간(base_time분)까지 주차 가능하고,
        이후에는 추가단위시간(add_time분)마다 추가요금(add_fee)이 붙는다.
        일 최대 요금(day_max_fee)이 있으면 그 금액을 넘지 않는다.

    >>> estimate_fee(2, base_fee=430, base_time=5, add_fee=430, add_time=5)
    10320
    >>> estimate_fee(1, base_fee=0, base_time=0, add_fee=0, add_time=0)   # 무료 주차장
    0
    """
    base_fee = _to_float(base_fee)
    base_time = _to_float(base_time)
    add_fee = _to_float(add_fee)
    add_time = _to_float(add_time)
    day_max = _to_float(day_max_fee)

    if base_fee <= 0 and add_fee <= 0:
        return 0  # 무료 주차장

    total_minutes = hours * 60

    # 기본시간 안에 끝나면 기본요금만
    if total_minutes <= base_time or add_time <= 0:
        return int(base_fee)

    extra_minutes = total_minutes - base_time
    # 추가 단위시간은 올림 처리 (5분 단위면 6분 주차 시 2단위 부과)
    units = -(-extra_minutes // add_time)  # ceil division
    total = base_fee + units * add_fee

    if day_max > 0:
        total = min(total, day_max)

    return int(total)


# ---------------------------------------------------------------------------
# 2) 지금 운영 중인지 판별
# ---------------------------------------------------------------------------
def _hhmm_to_minutes(hhmm: float | None) -> int | None:
    """HHMM 정수(예: 900 -> 09:00, 2400 -> 24:00)를 자정 기준 분으로 변환.

    pandas.NA / None / 변환 불가 값은 전부 None으로 돌려준다 (정보 없음).
    """
    if hhmm is None:
        return None
    try:
        if pd.isna(hhmm):
            return None
        value = int(hhmm)
    except (TypeError, ValueError):
        return None
    return (value // 100) * 60 + (value % 100)


def is_open_now(row: pd.Series, now: datetime | None = None) -> bool:
    """해당 주차장이 지금 시각에 운영 중인지 판정.

    평일/주말 컬럼을 요일에 따라 골라서 비교한다.
    운영시간 정보가 없으면 판단 불가이므로 True(=일단 후보에 포함)로 둔다.
    """
    now = now or datetime.now()
    is_weekend = now.weekday() >= 5  # 5=토, 6=일

    start_col = "weekend_start" if is_weekend else "weekday_start"
    end_col = "weekend_end" if is_weekend else "weekday_end"

    start = _hhmm_to_minutes(row.get(start_col))
    end = _hhmm_to_minutes(row.get(end_col))

    if start is None or end is None:
        return True  # 정보 없음 -> 배제하지 않음

    # 0000~2400 = 24시간 운영
    if start == 0 and end >= 1440:
        return True
    # 0000~0000 = 해당 요일 미운영
    if start == 0 and end == 0:
        return False

    current = now.hour * 60 + now.minute

    if start <= end:
        return start <= current <= end
    # 종료시각이 시작보다 작으면 자정을 넘겨 운영 (예: 2200~0600)
    return current >= start or current <= end


# ---------------------------------------------------------------------------
# 3) 개별 점수 (모두 0~1, 클수록 좋음)
# ---------------------------------------------------------------------------
def distance_score(distance_km: pd.Series, radius_km: float) -> pd.Series:
    """가까울수록 1에 가깝다. 반경 밖이면 0."""
    return (1 - distance_km / radius_km).clip(lower=0, upper=1)


def availability_score(df: pd.DataFrame) -> pd.Series:
    """여유가 많을수록 1에 가깝다.

    실시간 데이터가 없는 주차장은 0.5(중립)를 준다 — 정보가 없다는 이유로
    불이익을 주거나 유리하게 만들지 않기 위해서다.
    """
    if "available" not in df.columns or "capacity" not in df.columns:
        return pd.Series(0.5, index=df.index)

    capacity = pd.to_numeric(df["capacity"], errors="coerce")
    available = pd.to_numeric(df["available"], errors="coerce")

    score = (available / capacity).clip(0, 1)
    return score.fillna(0.5)


def fee_score(estimated_fee: pd.Series) -> pd.Series:
    """저렴할수록 1에 가깝다. 후보군 내 최고 요금을 기준으로 정규화."""
    max_fee = estimated_fee.max()
    if pd.isna(max_fee) or max_fee <= 0:
        return pd.Series(1.0, index=estimated_fee.index)  # 전부 무료
    return 1 - (estimated_fee / max_fee)


# ---------------------------------------------------------------------------
# 4) 종합 추천 점수
# ---------------------------------------------------------------------------
def rank_parking_lots(
    df: pd.DataFrame,
    radius_km: float,
    hours: float = 2.0,
    w_distance: float = 0.5,
    w_availability: float = 0.3,
    w_fee: float = 0.2,
    only_open: bool = True,
    now: datetime | None = None,
) -> pd.DataFrame:
    """주차장 후보에 예상요금·점수를 붙이고 추천 순위대로 정렬해 반환.

    df에 필요한 컬럼: distance_km, base_fee, base_time, add_fee, add_time
    (선택) capacity, available, weekday_start/end, weekend_start/end

    반환 컬럼 추가: estimated_fee, is_open, score_distance, score_availability,
                   score_fee, total_score
    """
    if df.empty:
        return df.assign(estimated_fee=[], total_score=[])

    out = df.copy()

    # 예상 요금
    out["estimated_fee"] = out.apply(
        lambda r: estimate_fee(
            hours,
            r.get("base_fee"),
            r.get("base_time"),
            r.get("add_fee"),
            r.get("add_time"),
            r.get("day_max_fee"),
        ),
        axis=1,
    )

    # 운영 여부
    out["is_open"] = out.apply(lambda r: is_open_now(r, now), axis=1)
    if only_open:
        out = out[out["is_open"]]
        if out.empty:
            return out

    # 개별 점수
    out["score_distance"] = distance_score(out["distance_km"], radius_km)
    out["score_availability"] = availability_score(out)
    out["score_fee"] = fee_score(out["estimated_fee"])

    # 가중치를 전부 0으로 내리면 점수가 전부 0이 되어 순위가 무의미해진다 -> 균등 가중치로
    if w_distance + w_availability + w_fee <= 0:
        w_distance = w_availability = w_fee = 1.0

    # 가중치 정규화 (합이 1이 되도록) - 슬라이더 조합이 뭐든 점수 범위가 0~1로 유지됨
    total_weight = w_distance + w_availability + w_fee

    out["total_score"] = (
        out["score_distance"] * w_distance
        + out["score_availability"] * w_availability
        + out["score_fee"] * w_fee
    ) / total_weight

    return out.sort_values("total_score", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# 5) 표시용 텍스트 (지도 말풍선 / 표 / DB의 fee·operation_time 컬럼)
# ---------------------------------------------------------------------------
def format_fee(row: pd.Series) -> str:
    """요금 컬럼들을 사람이 읽는 한 줄로 만든다.

    >>> format_fee(pd.Series({"base_fee": 430, "base_time": 5, "add_fee": 430, "add_time": 5}))
    '기본 5분 430원 / 추가 5분당 430원'
    """
    base_fee = _to_float(row.get("base_fee"))
    base_time = _to_float(row.get("base_time"))
    add_fee = _to_float(row.get("add_fee"))
    add_time = _to_float(row.get("add_time"))
    day_max = _to_float(row.get("day_max_fee"))

    if base_fee <= 0 and add_fee <= 0:
        return "무료"

    parts = [f"기본 {base_time:.0f}분 {base_fee:,.0f}원"]
    if add_fee > 0 and add_time > 0:
        parts.append(f"추가 {add_time:.0f}분당 {add_fee:,.0f}원")
    if day_max > 0:
        parts.append(f"일 최대 {day_max:,.0f}원")
    return " / ".join(parts)


def format_hours(row: pd.Series) -> str:
    """평일/주말 운영시간을 'HH:MM~HH:MM' 형태의 한 줄로 만든다."""

    def one(start_col: str, end_col: str) -> str | None:
        start = _hhmm_to_minutes(row.get(start_col))
        end = _hhmm_to_minutes(row.get(end_col))
        if start is None or end is None:
            return None
        if start == 0 and end >= 1440:
            return "24시간"
        if start == 0 and end == 0:
            return "미운영"
        return f"{start // 60:02d}:{start % 60:02d}~{end // 60:02d}:{end % 60:02d}"

    weekday = one("weekday_start", "weekday_end")
    weekend = one("weekend_start", "weekend_end")

    if weekday is None and weekend is None:
        return "운영시간 정보없음"
    if weekday == weekend:
        return f"매일 {weekday}"
    return " / ".join(
        text for text in (f"평일 {weekday}" if weekday else None,
                          f"주말 {weekend}" if weekend else None)
        if text
    )


def format_availability(row: pd.Series) -> str:
    """실시간 주차 여유를 '여유 863/1260면' 형태로 표시. 정보 없으면 총 면수만."""
    capacity = _to_float(row.get("capacity"))
    available = row.get("available")

    try:
        has_available = available is not None and not pd.isna(available)
    except (TypeError, ValueError):
        has_available = False

    if has_available and capacity > 0:
        return f"여유 {float(available):,.0f}/{capacity:,.0f}면"
    if capacity > 0:
        return f"총 {capacity:,.0f}면"
    return "주차면 정보없음"


# ---------------------------------------------------------------------------
# 자체 테스트
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # 요금 계산 검증
    assert estimate_fee(2, 430, 5, 430, 5) == 10320, "2시간=기본1회+23단위"
    assert estimate_fee(0.05, 430, 5, 430, 5) == 430, "기본시간 이내는 기본요금만"
    assert estimate_fee(1, 0, 0, 0, 0) == 0, "무료 주차장"
    assert estimate_fee(10, 430, 5, 430, 5, day_max_fee=20000) == 20000, "일 최대요금 상한"
    assert estimate_fee(1, 1000, 30, 500, 10) == 2500, "기본30분+추가10분×3"

    # 회귀 테스트: DataFrame의 Int64 컬럼에서 꺼낸 값은 None이 아니라 pd.NA 다.
    # 예전 구현은 `if day_max_fee and ...` 때문에 여기서 TypeError가 났었다.
    assert estimate_fee(2, 430, 5, 430, 5, day_max_fee=pd.NA) == 10320, "day_max_fee가 NA"
    assert estimate_fee(2, pd.NA, pd.NA, pd.NA, pd.NA) == 0, "요금 전체가 NA면 무료 처리"
    na_row = pd.DataFrame({"v": [1, None]}, dtype="Int64")["v"]
    assert estimate_fee(2, 430, 5, 430, 5, day_max_fee=na_row.iloc[1]) == 10320, \
        "Int64 컬럼에서 꺼낸 결측값"
    assert _hhmm_to_minutes(pd.NA) is None, "운영시각이 NA면 정보 없음 처리"

    # 운영시간 판별 검증
    assert is_open_now(pd.Series({"weekday_start": 0, "weekday_end": 2400}),
                       datetime(2026, 7, 27, 3, 0)) is True, "24시간 운영"
    assert is_open_now(pd.Series({"weekday_start": 900, "weekday_end": 1900}),
                       datetime(2026, 7, 27, 10, 0)) is True, "운영시간 내"
    assert is_open_now(pd.Series({"weekday_start": 900, "weekday_end": 1900}),
                       datetime(2026, 7, 27, 20, 0)) is False, "운영시간 외"
    assert is_open_now(pd.Series({"weekday_start": 2200, "weekday_end": 600}),
                       datetime(2026, 7, 27, 23, 0)) is True, "자정 넘김 운영"
    assert is_open_now(pd.Series({})) is True, "정보 없으면 배제 안 함"

    # 랭킹 검증
    sample = pd.DataFrame([
        {"parking_name": "가까운데 비쌈", "distance_km": 0.1, "capacity": 100, "available": 50,
         "base_fee": 1000, "base_time": 5, "add_fee": 1000, "add_time": 5,
         "weekday_start": 0, "weekday_end": 2400},
        {"parking_name": "멀지만 무료", "distance_km": 0.9, "capacity": 100, "available": 90,
         "base_fee": 0, "base_time": 0, "add_fee": 0, "add_time": 0,
         "weekday_start": 0, "weekday_end": 2400},
        {"parking_name": "닫힘", "distance_km": 0.05, "capacity": 100, "available": 99,
         "base_fee": 0, "base_time": 0, "add_fee": 0, "add_time": 0,
         "weekday_start": 0, "weekday_end": 0},
    ])

    ranked = rank_parking_lots(sample, radius_km=1.0, hours=2,
                               now=datetime(2026, 7, 27, 14, 0))
    assert "닫힘" not in ranked["parking_name"].values, "미운영 주차장은 제외되어야 함"
    assert len(ranked) == 2
    assert ranked["total_score"].between(0, 1).all(), "점수는 0~1 범위"
    assert ranked["total_score"].is_monotonic_decreasing, "점수 내림차순 정렬"

    # 거리 가중치를 100%로 주면 가장 가까운 곳이 1위여야 한다
    by_distance = rank_parking_lots(sample, 1.0, 2, w_distance=1, w_availability=0,
                                    w_fee=0, now=datetime(2026, 7, 27, 14, 0))
    assert by_distance.iloc[0]["parking_name"] == "가까운데 비쌈"

    # 요금 가중치를 100%로 주면 무료 주차장이 1위여야 한다
    by_fee = rank_parking_lots(sample, 1.0, 2, w_distance=0, w_availability=0,
                               w_fee=1, now=datetime(2026, 7, 27, 14, 0))
    assert by_fee.iloc[0]["parking_name"] == "멀지만 무료"

    # 가중치를 전부 0으로 내려도 점수가 전부 0이 되지 않고 균등 가중치로 동작해야 한다
    all_zero = rank_parking_lots(sample, 1.0, 2, w_distance=0, w_availability=0,
                                 w_fee=0, now=datetime(2026, 7, 27, 14, 0))
    assert all_zero["total_score"].max() > 0, "가중치 0 조합에서도 순위가 나와야 함"
    assert all_zero["total_score"].between(0, 1).all()

    # 표시용 텍스트 검증
    assert format_fee(pd.Series({"base_fee": 430, "base_time": 5, "add_fee": 430, "add_time": 5})) \
        == "기본 5분 430원 / 추가 5분당 430원"
    assert format_fee(pd.Series({"base_fee": 0, "add_fee": 0})) == "무료"
    assert format_fee(pd.Series({"base_fee": pd.NA, "add_fee": pd.NA})) == "무료", "NA도 안전하게"
    assert format_hours(pd.Series({"weekday_start": 0, "weekday_end": 2400,
                                   "weekend_start": 0, "weekend_end": 2400})) == "매일 24시간"
    assert format_hours(pd.Series({"weekday_start": 900, "weekday_end": 1900,
                                   "weekend_start": 0, "weekend_end": 0})) \
        == "평일 09:00~19:00 / 주말 미운영"
    assert format_hours(pd.Series({})) == "운영시간 정보없음"
    assert format_availability(pd.Series({"capacity": 1260, "available": 863})) == "여유 863/1,260면"
    assert format_availability(pd.Series({"capacity": 1260, "available": pd.NA})) == "총 1,260면"
    assert format_availability(pd.Series({})) == "주차면 정보없음"

    print("✅ 추천 로직 테스트 전부 통과")
    print(ranked[["parking_name", "distance_km", "estimated_fee", "total_score"]].to_string(index=False))
