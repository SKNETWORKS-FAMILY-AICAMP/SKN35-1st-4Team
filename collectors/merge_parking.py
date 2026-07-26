"""
[담당: 승희] 여러 소스의 주차장 데이터를 하나의 테이블로 합치는 모듈.

같은 주차장이 소스마다 **다른 이름**으로 들어있다.
    서울시 공영 : "세종로 공영주차장(시)"
    표준데이터  : "세종로공영주차장"

그냥 concat 하면 지도에 마커가 두 개 찍히고 추천 순위도 왜곡된다.
    판정 기준: 이름 정규화 후 일치  AND  좌표가 50m 이내

중복을 지울 때 그냥 버리지 않고, 남기는 행의 빈 칸을 버리는 행 값으로 채운다(coalesce).
소스마다 가진 정보가 달라서(공영엔 요금이 자세하고, 표준데이터엔 좌표가 있고 …)
합치면 정보가 더 풍부해지기 때문이다.

자체 테스트
    uv run python collectors/merge_parking.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from common.geo import haversine_km  # noqa: E402

# 통합 테이블의 최종 컬럼 순서 (DB의 PUBLIC/PRIVATE_PARKING_LOT 과 동일)
TABLE_COLUMNS = [
    "parking_id", "parking_name", "lot_category", "lot_type", "operation_rule",
    "district", "address", "latitude", "longitude", "phone", "capacity",
    "pay_type", "base_fee", "base_time", "add_fee", "add_time",
    "day_max_fee", "monthly_fee",
    "weekday_start", "weekday_end", "weekend_start", "weekend_end",
    "holiday_start", "holiday_end", "source",
]

# 중복일 때 어느 소스를 '대표'로 남길지 (숫자가 작을수록 우선)
SOURCE_PRIORITY = {"seoul_public": 0, "standard": 1, "crawl": 2}

DEFAULT_MERGE_DISTANCE_M = 50

# 이름 정규화 때 떼어낼 접미사 (긴 것부터 지워야 '공영주차장'이 '주차장'보다 먼저 걸린다)
_NAME_SUFFIXES = ("공영주차장", "노외주차장", "노상주차장", "부설주차장", "주차장", "주차빌딩")


# ---------------------------------------------------------------------------
# 1) 이름 정규화
# ---------------------------------------------------------------------------
def normalize_name(name: str | None) -> str:
    """비교용으로 주차장 이름을 정규화.

    괄호 내용/공백/특수문자를 없애고 '공영주차장' 같은 접미사를 떼어낸다.

    >>> normalize_name("세종로 공영주차장(시)")
    '세종로'
    >>> normalize_name("세종로공영주차장")
    '세종로'
    >>> normalize_name("청계2(북2) 공영주차장(시)")
    '청계2'
    """
    if name is None:
        return ""
    try:
        if pd.isna(name):  # NaN / pd.NA
            return ""
    except (TypeError, ValueError):
        pass

    text = str(name)
    text = re.sub(r"\([^)]*\)", "", text)          # 괄호와 그 안의 내용 제거
    text = re.sub(r"[\s\-_·,./]", "", text)        # 공백·구분기호 제거

    for suffix in _NAME_SUFFIXES:
        if text.endswith(suffix) and len(text) > len(suffix):
            text = text[: -len(suffix)]
            break

    return text.lower()


# ---------------------------------------------------------------------------
# 2) 중복 판정 · 병합
# ---------------------------------------------------------------------------
def _completeness(df: pd.DataFrame) -> pd.Series:
    """행마다 값이 채워진 컬럼 수 (정보가 많은 행을 대표로 남기기 위한 기준)."""
    return df.notna().sum(axis=1)


def normalize_address(address: str | None) -> str:
    """비교용 주소 정규화. '서울특별시'/'서울시' 접두어와 공백을 없앤다.

    >>> normalize_address("서울특별시 종로구 세종로 80-1")
    '종로구세종로80-1'
    """
    if address is None:
        return ""
    try:
        if pd.isna(address):
            return ""
    except (TypeError, ValueError):
        pass

    text = re.sub(r"^서울(특별시|시)?", "", str(address).strip())
    return re.sub(r"\s", "", text).lower()


def _is_same_place(row_a: pd.Series, row_b: pd.Series, distance_m: int) -> bool:
    """두 행이 같은 주차장인지 판정 (이름 정규화 결과가 같다는 전제).

    - 좌표가 둘 다 있으면 거리로 판정한다.
    - 한쪽이라도 좌표가 없으면 주소까지 같아야 같은 곳으로 본다.
      '망원노상공영주차장'처럼 하나의 이름이 여러 구간(주차장코드)으로 나뉘어 있고
      좌표도 없는 경우가 많아서, 이름만 믿고 합치면 서로 다른 구간이 사라진다.
    """
    coords = (row_a.get("latitude"), row_a.get("longitude"),
              row_b.get("latitude"), row_b.get("longitude"))
    if not any(v is None or pd.isna(v) for v in coords):
        distance_km = haversine_km(float(coords[0]), float(coords[1]),
                                   float(coords[2]), float(coords[3]))
        return distance_km * 1000 <= distance_m

    address_a = normalize_address(row_a.get("address"))
    address_b = normalize_address(row_b.get("address"))
    return bool(address_a) and address_a == address_b


def _coalesce(primary: pd.Series, others: list[pd.Series]) -> pd.Series:
    """대표 행의 빈 칸을 나머지 행의 값으로 채운다."""
    merged = primary.copy()
    for other in others:
        merged = merged.where(merged.notna(), other)
    return merged


def dedupe(df: pd.DataFrame, distance_m: int = DEFAULT_MERGE_DISTANCE_M) -> pd.DataFrame:
    """이름 정규화 + 좌표 근접으로 중복 주차장을 하나로 합친다."""
    if df.empty:
        return df.copy()

    work = df.copy()
    work["_name_key"] = work["parking_name"].map(normalize_name)
    work["_priority"] = work.get("source", pd.Series("", index=work.index)).map(
        lambda s: SOURCE_PRIORITY.get(s, 99)
    )
    work["_completeness"] = _completeness(df)

    # 우선순위 높고 정보 많은 행이 먼저 오도록 정렬 -> 각 클러스터의 첫 행이 대표가 된다
    work = work.sort_values(["_priority", "_completeness"], ascending=[True, False])

    kept: list[pd.Series] = []
    for _, group in work.groupby("_name_key", sort=False):
        # 이름이 비어 있으면 비교 자체가 불가능하므로 전부 남긴다
        if group["_name_key"].iloc[0] == "":
            kept.extend(row for _, row in group.iterrows())
            continue

        clusters: list[list[pd.Series]] = []
        for _, row in group.iterrows():
            for cluster in clusters:
                if _is_same_place(cluster[0], row, distance_m):
                    cluster.append(row)
                    break
            else:
                clusters.append([row])

        kept.extend(_coalesce(cluster[0], cluster[1:]) for cluster in clusters)

    result = pd.DataFrame(kept).drop(columns=["_name_key", "_priority", "_completeness"])
    return result.reset_index(drop=True)


# ---------------------------------------------------------------------------
# 3) 최종 스키마 정리
# ---------------------------------------------------------------------------
def to_table_schema(df: pd.DataFrame) -> pd.DataFrame:
    """TABLE_COLUMNS 순서로 정리한다. 없는 컬럼은 결측으로 채운다."""
    out = df.copy()
    for col in TABLE_COLUMNS:
        if col not in out.columns:
            out[col] = pd.NA
    return out[TABLE_COLUMNS].reset_index(drop=True)


def merge_sources(*frames: pd.DataFrame, distance_m: int = DEFAULT_MERGE_DISTANCE_M) -> pd.DataFrame:
    """여러 소스의 DataFrame을 합치고 중복 제거 후 최종 스키마로 정리."""
    usable = [f for f in frames if f is not None and not f.empty]
    if not usable:
        return to_table_schema(pd.DataFrame())
    combined = pd.concat(usable, ignore_index=True)
    return to_table_schema(dedupe(combined, distance_m))


# ---------------------------------------------------------------------------
# 자체 테스트
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # 이름 정규화
    assert normalize_name("세종로 공영주차장(시)") == "세종로"
    assert normalize_name("세종로공영주차장") == "세종로"
    assert normalize_name("청계2(북2) 공영주차장(시)") == "청계2"
    assert normalize_name("낙원상가 주차장") == "낙원상가"
    assert normalize_name("주차장") == "주차장", "접미사만 남는 이름은 그대로 둔다"
    assert normalize_name(None) == ""
    assert normalize_name(pd.NA) == ""

    # 주소 정규화
    assert normalize_address("서울특별시 종로구 세종로 80-1") == "종로구세종로80-1"
    assert normalize_address("종로구 세종로 80-1") == "종로구세종로80-1"
    assert normalize_address(None) == ""

    # 좌표가 없으면 주소가 같아야만 합쳐진다 (노상주차장 구간이 뭉개지는 것 방지)
    no_coord = pd.DataFrame([
        {"parking_id": "A", "parking_name": "망원노상공영주차장(구)",
         "address": "마포구 망원동 457-31", "source": "seoul_public"},
        {"parking_id": "B", "parking_name": "망원노상공영주차장(구)",
         "address": "마포구 망원동 454-26", "source": "seoul_public"},
        {"parking_id": "C", "parking_name": "망원노상 공영주차장 (구)",
         "address": "서울특별시 마포구 망원동 457-31", "source": "standard"},
    ])
    assert len(merge_sources(no_coord)) == 2, "주소가 다르면 남고, 같으면 합쳐져야 함"

    public = pd.DataFrame([
        {"parking_id": "171721", "parking_name": "세종로 공영주차장(시)", "lot_category": "공영",
         "address": "종로구 세종로 80-1", "latitude": 37.57340, "longitude": 126.97588,
         "capacity": 1260, "base_fee": 430, "base_time": 5, "source": "seoul_public"},
        {"parking_id": "171730", "parking_name": "종묘주차장 공영주차장(시)", "lot_category": "공영",
         "address": "종로구 훈정동 2-0", "latitude": 37.57150, "longitude": 126.99497,
         "capacity": 1312, "base_fee": 400, "base_time": 5, "source": "seoul_public"},
    ])
    standard = pd.DataFrame([
        # 같은 곳 (이름 정규화 일치 + 30m 이내) -> 병합되어야 함. phone은 여기에만 있다.
        {"parking_id": "STD-1", "parking_name": "세종로공영주차장", "lot_category": "공영",
         "address": "서울특별시 종로구 세종로 80-1", "latitude": 37.57365, "longitude": 126.97588,
         "capacity": 1260, "phone": "02-2290-6566", "source": "standard"},
        # 이름은 같지만 2km 넘게 떨어진 다른 주차장 -> 따로 남아야 함
        {"parking_id": "STD-2", "parking_name": "세종로 주차장", "lot_category": "민영",
         "address": "서울특별시 중구 어딘가", "latitude": 37.55000, "longitude": 126.97588,
         "capacity": 30, "source": "standard"},
        {"parking_id": "STD-3", "parking_name": "광화문D타워", "lot_category": "민영",
         "address": "서울특별시 종로구 청진동", "latitude": 37.5711, "longitude": 126.9780,
         "capacity": 300, "source": "standard"},
    ])

    merged = merge_sources(public, standard)
    names = list(merged["parking_name"])
    assert len(merged) == 4, f"세종로 2건이 1건으로 합쳐져야 함: {names}"
    assert "세종로 공영주차장(시)" in names, "대표는 우선순위 높은 서울시 공영 이름"
    assert "세종로공영주차장" not in names

    sejong = merged[merged["parking_name"] == "세종로 공영주차장(시)"].iloc[0]
    assert sejong["phone"] == "02-2290-6566", "표준데이터에만 있던 전화번호가 채워져야 함"
    assert sejong["source"] == "seoul_public"

    assert (merged["lot_category"] == "민영").sum() == 2, "멀리 떨어진 동명 주차장은 남는다"
    assert list(merged.columns) == TABLE_COLUMNS

    # 빈 입력도 안전해야 한다
    assert merge_sources().empty
    assert list(merge_sources(pd.DataFrame()).columns) == TABLE_COLUMNS

    print("✅ 병합/중복제거 테스트 전부 통과")
    print(merged[["parking_name", "lot_category", "capacity", "phone", "source"]].to_string(index=False))
