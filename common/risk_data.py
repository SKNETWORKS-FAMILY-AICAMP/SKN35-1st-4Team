"""
[담당: 승희] 불법주정차 위험도 판정용 데이터 로더.

두 팀원 데이터를 읽어서 "지금 이 좌표가 단속 위험 구역인가"를 계산한다.
    단속 다발구역 : ENFORCEMENT_HISTORY (치훈) - 주소별 단속 건수 집계
    단속 CCTV     : CCTV_INFO (종원/jw)

DB가 없으면 정제 CSV를 읽고, 그것도 없으면 빈 DataFrame을 돌려준다.
데이터가 없어도 주차장 검색은 그대로 동작해야 하므로 절대 예외를 던지지 않는다.

⚠ 판정 결과는 "과거 단속 기록 기준 참고값"이지 합법/불법 판단이 아니다.
   기록이 없다고 주차해도 되는 곳이라는 뜻이 아니다.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# 팀원 스크립트가 저장하는 경로
CCTV_CSV = ROOT / "data/cleaned/cctv_cleaned.csv"

# 단속 이력은 파일명이 제각각이라 후보를 순서대로 찾는다 (먼저 발견되는 것을 쓴다)
ENFORCEMENT_CANDIDATES = (
    ROOT / "data/cleaned/enforcement_history.csv",
    ROOT / "data/cleaned/종로구_단속정보_통합_데이터.csv",
)

# 원본 한글 컬럼 -> 내부 이름. 단속일+단속시간은 합쳐서 enforced_at 을 만든다.
ENFORCEMENT_COLUMN_MAP = {
    "구주소": "address",
    "도로명": "road_address",
    "위도": "latitude",
    "경도": "longitude",
    "단속일시": "enforced_at",
}

# 위험도 판정 기준 (반경 안의 누적 단속 건수 / 가장 가까운 CCTV까지 거리)
DEFAULT_RADIUS_M = 100
DANGER_ENFORCEMENTS = 10
DANGER_CCTV_M = 50
CAUTION_CCTV_M = 150

EMPTY_HOTSPOTS = pd.DataFrame(
    columns=["address", "latitude", "longitude", "violation_count"]
)
EMPTY_CCTV = pd.DataFrame(columns=["address", "latitude", "longitude", "organization"])
EMPTY_SLOTS = pd.DataFrame(columns=["latitude", "longitude", "hour", "weekday", "count"])


# ---------------------------------------------------------------------------
# 거리 계산 (하버사인 벡터 버전)
# ---------------------------------------------------------------------------
def distances_m(lat: float, lng: float, df: pd.DataFrame) -> np.ndarray:
    """기준 좌표에서 df 각 행까지의 거리(m). 좌표가 없는 행은 inf."""
    if df.empty:
        return np.array([])

    lat2 = pd.to_numeric(df["latitude"], errors="coerce").to_numpy(dtype=float)
    lng2 = pd.to_numeric(df["longitude"], errors="coerce").to_numpy(dtype=float)

    p1, p2 = np.radians(lat), np.radians(lat2)
    dp = np.radians(lat2 - lat)
    dl = np.radians(lng2 - lng)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    metres = 2 * 6_371_000 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
    return np.where(np.isnan(metres), np.inf, metres)


# ---------------------------------------------------------------------------
# 로더
# ---------------------------------------------------------------------------
def _read_sql(sql: str) -> pd.DataFrame | None:
    """DB에서 읽는다. DB 설정이 아예 없으면 None(=CSV로 폴백).

    설정이 있는데 실패하면 예외를 그대로 올린다. 예전에는 여기서도 None을
    돌려줘 CSV로 조용히 넘어갔는데, 그러면 화면은 멀쩡해 보이면서 실제로는
    옛날 CSV를 보여주게 된다. 적재가 덜 됐거나 접속이 끊긴 걸 눈치채지
    못하는 게 더 위험해서, 지금은 티 나게 실패시킨다.
    """
    if not config.is_db_configured():
        return None

    from common.db import DataSourceError, read_sql

    try:
        df = read_sql(sql)
    except Exception as exc:  # noqa: BLE001 - 원인 무관하게 사용자에게 알린다
        raise DataSourceError(
            f"DB에서 데이터를 읽지 못했습니다 ({type(exc).__name__}). "
            "테이블이 비었으면 `uv run python loaders/load_all.py`, "
            "접속이 문제면 .env의 DB_* 값을 확인하세요."
        ) from exc

    # 비어 있어도 그대로 돌려준다. 여기서 None을 주면 호출부가 CSV로 넘어가
    # "적재가 안 된 상태"가 옛 CSV 데이터에 가려진다.
    return df


def _read_csv(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
    except (OSError, ValueError):
        return None
    return df if not df.empty else None


def enforcement_path() -> Path | None:
    """단속 이력 CSV 경로. 후보 중 먼저 존재하는 것."""
    for path in ENFORCEMENT_CANDIDATES:
        if path.exists():
            return path
    return None


def _read_enforcement() -> pd.DataFrame | None:
    """단속 이력 CSV를 읽어 address/latitude/longitude/enforced_at 로 통일.

    원본 컬럼이 두 가지다.
        정제본  : address, enforced_at, latitude, longitude
        서울시  : 구주소, 단속일(20250101), 단속시간(00:00:05), 위도, 경도
    """
    path = enforcement_path()
    if path is None:
        return None

    df = _read_csv(path)
    if df is None:
        return None

    # 단속일 + 단속시간 -> enforced_at
    if {"단속일", "단속시간"} <= set(df.columns):
        day = pd.to_numeric(df["단속일"], errors="coerce")
        df = df[day.notna()].copy()
        df["단속일시"] = (
            day[day.notna()].astype("int64").astype(str)
            + " "
            + df["단속시간"].astype(str)
        )

    df = df.rename(columns=ENFORCEMENT_COLUMN_MAP)
    need = {"address", "latitude", "longitude"}
    if not need <= set(df.columns):
        return None

    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    df = df.dropna(subset=["latitude", "longitude"])
    return df if not df.empty else None


def _mtime(path: Path) -> float:
    """파일 수정 시각. 없으면 0.

    캐시 키로 쓴다. 팀원이 수집기를 돌려 CSV를 새로 만들면 이 값이 바뀌면서
    캐시가 자동으로 무효화된다. 이게 없으면 "데이터 없음"이 캐시된 채로
    ttl(30분)이 지나거나 앱을 재시작할 때까지 새 파일이 반영되지 않는다.
    """
    return path.stat().st_mtime if path.exists() else 0.0


def load_hotspots() -> tuple[pd.DataFrame, str]:
    """단속 다발구역(주소별 집계) + 출처 설명."""
    path = enforcement_path()
    return _load_hotspots(_mtime(path) if path else 0.0)


def load_cctv() -> tuple[pd.DataFrame, str]:
    """단속 CCTV 위치 + 출처 설명."""
    return _load_cctv(_mtime(CCTV_CSV))


@st.cache_data(ttl=1800, show_spinner=False)
def _load_hotspots(csv_mtime: float) -> tuple[pd.DataFrame, str]:
    from_db = _read_sql(
        "SELECT address, AVG(latitude) AS latitude, AVG(longitude) AS longitude, "
        "COUNT(*) AS violation_count "
        "FROM ENFORCEMENT_HISTORY WHERE latitude IS NOT NULL "
        "GROUP BY address"
    )
    if from_db is not None:
        return from_db, f"단속 다발구역: DB ENFORCEMENT_HISTORY ({len(from_db):,}곳)"

    raw = _read_enforcement()
    if raw is not None:
        hotspots = raw.groupby("address", as_index=False).agg(
            latitude=("latitude", "mean"),
            longitude=("longitude", "mean"),
            violation_count=("address", "size"),
        )
        name = enforcement_path().name
        return hotspots, f"단속 다발구역: {name} ({len(hotspots):,}곳 / {len(raw):,}건)"

    return EMPTY_HOTSPOTS.copy(), "단속 다발구역: 데이터 없음"


@st.cache_data(ttl=1800, show_spinner=False)
def _load_cctv(csv_mtime: float) -> tuple[pd.DataFrame, str]:
    from_db = _read_sql(
        "SELECT address, latitude, longitude, organization "
        "FROM CCTV_INFO WHERE latitude IS NOT NULL"
    )
    if from_db is not None:
        return from_db, f"단속 CCTV: DB CCTV_INFO ({len(from_db):,}대)"

    raw = _read_csv(CCTV_CSV)
    if raw is not None and {"latitude", "longitude"} <= set(raw.columns):
        cctv = raw.dropna(subset=["latitude", "longitude"]).copy()
        if "organization" not in cctv.columns:
            cctv["organization"] = pd.NA
        return cctv, f"단속 CCTV: {CCTV_CSV.name} ({len(cctv):,}대)"

    return EMPTY_CCTV.copy(), "단속 CCTV: 데이터 없음"


# ---------------------------------------------------------------------------
# 위험도 판정
# ---------------------------------------------------------------------------
def watch_detail(
    lat: float,
    lng: float,
    hotspots: pd.DataFrame,
    cctv: pd.DataFrame,
    radius_m: int = DEFAULT_RADIUS_M,
) -> list[dict]:
    """감시 유형을 나눠서 각각의 상태와 대응 요령을 돌려준다.

    두 위험은 적발 방식이 다르므로 나눠서 알려준다.
        고정 CCTV : 24시간 자동 촬영
        순찰 단속 : 단속원 순찰 중 적발
    어느 쪽이든 결론은 같다 — 주차하면 안 되는 자리다.
    """
    details = []

    cctv_d = distances_m(lat, lng, cctv)
    if len(cctv_d) and np.isfinite(cctv_d).any():
        nearest = float(np.min(cctv_d))
        within = int((cctv_d <= radius_m).sum())
        if nearest <= DANGER_CCTV_M:
            level, action = "위험", "24시간 자동 촬영 중입니다. 여기 세우면 과태료 대상입니다."
        elif nearest <= CAUTION_CCTV_M:
            level, action = "주의", "근처에 단속 카메라가 있습니다. 주차 구역이 아니면 피하세요."
        else:
            level, action = "낮음", "반경 안에 카메라 기록은 없지만 주차 가능 여부와는 무관합니다."
        details.append({
            "type": "고정 CCTV",
            "icon": ":material/videocam:",
            "level": level,
            "summary": f"가장 가까운 카메라 {nearest:,.0f}m · 반경 내 {within}대",
            "action": action,
        })

    hotspot_d = distances_m(lat, lng, hotspots)
    if len(hotspot_d) and np.isfinite(hotspot_d).any():
        near = hotspots[hotspot_d <= radius_m]
        count = int(pd.to_numeric(near["violation_count"], errors="coerce").fillna(0).sum())
        if count >= DANGER_ENFORCEMENTS:
            level, action = "위험", "단속이 반복된 구역입니다. 주차장을 이용하세요."
        elif count > 0:
            level, action = "주의", "단속된 적이 있는 구역입니다. 주차 구역이 아니면 피하세요."
        else:
            level, action = "낮음", "반경 안에 단속 기록은 없지만 주차 가능 여부와는 무관합니다."
        details.append({
            "type": "순찰 단속",
            "icon": ":material/directions_walk:",
            "level": level,
            "summary": f"반경 내 누적 {count:,}건 · 다발구역 {len(near)}곳",
            "action": action,
        })

    return details


def assess_location(
    lat: float,
    lng: float,
    hotspots: pd.DataFrame,
    cctv: pd.DataFrame,
    radius_m: int = DEFAULT_RADIUS_M,
) -> dict:
    """좌표 하나에 대해 반경 안의 단속 이력·CCTV를 세어 등급을 매긴다.

    등급은 '위험 / 주의 / 기록 없음' 3단계다.
    마지막 등급을 '안전'이라 부르지 않는 이유: 단속 이력이 없는 것과
    합법 주차 구역인 것은 전혀 다른 이야기다.
    """
    hotspot_d = distances_m(lat, lng, hotspots)
    cctv_d = distances_m(lat, lng, cctv)

    near_hotspots = hotspots[hotspot_d <= radius_m] if len(hotspot_d) else hotspots.iloc[0:0]
    enforcement_count = (
        int(pd.to_numeric(near_hotspots["violation_count"], errors="coerce").fillna(0).sum())
        if not near_hotspots.empty
        else 0
    )

    nearest_hotspot_m = float(hotspot_d.min()) if len(hotspot_d) and np.isfinite(hotspot_d).any() else None
    nearest_hotspot = (
        hotspots.iloc[int(np.argmin(hotspot_d))]["address"] if nearest_hotspot_m is not None else None
    )
    nearest_cctv_m = float(cctv_d.min()) if len(cctv_d) and np.isfinite(cctv_d).any() else None
    cctv_count = int((cctv_d <= radius_m).sum()) if len(cctv_d) else 0

    if enforcement_count >= DANGER_ENFORCEMENTS or (
        nearest_cctv_m is not None and nearest_cctv_m <= DANGER_CCTV_M
    ):
        level, message = "위험", "단속이 반복되는 구역입니다. 아래 주차장을 이용하세요."
    elif enforcement_count > 0 or (
        nearest_cctv_m is not None and nearest_cctv_m <= CAUTION_CCTV_M
    ):
        level, message = "주의", "단속 이력·카메라가 근처에 있습니다. 주차 구역인지 확인하세요."
    else:
        level, message = "기록 없음", "단속 기록은 없지만 주차 가능한 곳이라는 뜻은 아닙니다."

    return {
        "level": level,
        "message": message,
        "radius_m": radius_m,
        "enforcement_count": enforcement_count,
        "hotspot_count": len(near_hotspots),
        "nearest_hotspot_m": nearest_hotspot_m,
        "nearest_hotspot": nearest_hotspot,
        "cctv_count": cctv_count,
        "nearest_cctv_m": nearest_cctv_m,
    }


# ---------------------------------------------------------------------------
# 시간대별 단속 패턴
# ---------------------------------------------------------------------------
# 하루 전체의 몇 %를 넘으면 "단속이 잦은 시간대"로 볼지
BUSY_SHARE = 0.08


def _slots_from_frame(raw: pd.DataFrame) -> pd.DataFrame:
    """단속 이력 원본 -> (좌표, 시간, 요일)별 건수."""
    df = raw.dropna(subset=["latitude", "longitude", "enforced_at"]).copy()
    df["enforced_at"] = pd.to_datetime(df["enforced_at"], errors="coerce")
    df = df.dropna(subset=["enforced_at"])
    if df.empty:
        return EMPTY_SLOTS.copy()

    df["hour"] = df["enforced_at"].dt.hour
    df["weekday"] = df["enforced_at"].dt.weekday  # 월=0 … 일=6
    return (
        df.groupby(["latitude", "longitude", "hour", "weekday"], as_index=False)
        .size()
        .rename(columns={"size": "count"})
    )


@st.cache_data(ttl=1800, show_spinner=False)
def _load_slots(csv_mtime: float) -> pd.DataFrame:
    # DB는 SQL에서 미리 집계한다 (단속 이력은 수백만 행이 될 수 있다).
    # MySQL DAYOFWEEK는 일=1이라 (+5)를 7로 나눈 나머지로 파이썬 요일(월=0)에 맞춘다.
    #
    # 나머지 연산에 % 대신 MOD()를 쓴다. pymysql은 파라미터 바인딩에 %s를 쓰기
    # 때문에 SQL 안의 %는 %%로 escape해야 하는데, params 없이 보내면 아무도
    # 되돌려주지 않아 %%가 그대로 DB에 도착해 문법 오류가 난다.
    from_db = _read_sql(
        "SELECT ROUND(latitude, 5) AS latitude, ROUND(longitude, 5) AS longitude, "
        "HOUR(enforced_at) AS hour, MOD(DAYOFWEEK(enforced_at) + 5, 7) AS weekday, "
        "COUNT(*) AS count "
        "FROM ENFORCEMENT_HISTORY "
        "WHERE latitude IS NOT NULL AND enforced_at IS NOT NULL "
        "GROUP BY 1, 2, 3, 4"
    )
    if from_db is not None:
        return from_db

    raw = _read_enforcement()
    if raw is not None and "enforced_at" in raw.columns:
        return _slots_from_frame(raw)
    return EMPTY_SLOTS.copy()


def load_slots() -> pd.DataFrame:
    """시간대별 단속 집계. 단속 이력이 없으면 빈 DataFrame."""
    path = enforcement_path()
    return _load_slots(_mtime(path) if path else 0.0)


def hour_profile(
    lat: float,
    lng: float,
    slots: pd.DataFrame,
    radius_m: int = DEFAULT_RADIUS_M,
    weekday: int | None = None,
) -> pd.Series:
    """반경 안 단속을 0~23시 건수로. weekday를 주면 그 요일만 센다."""
    empty = pd.Series(0, index=range(24), name="count")
    if slots.empty:
        return empty

    near = slots[distances_m(lat, lng, slots) <= radius_m]
    if weekday is not None:
        near = near[near["weekday"] == weekday]
    if near.empty:
        return empty

    counts = near.groupby("hour")["count"].sum()
    return counts.reindex(range(24), fill_value=0).astype(int).rename("count")


def time_advice(profile: pd.Series, now: datetime | None = None) -> dict | None:
    """지금 시간대가 위험한지 + 언제 안전해지는지(또는 위험해지는지).

    "여기 세워도 되나"만큼 중요한 게 "언제까지 괜찮나"다.
    같은 자리도 출근시간대와 심야의 단속 확률은 전혀 다르다.
    """
    total = int(profile.sum())
    if total == 0:
        return None

    now = now or datetime.now()
    threshold = max(1, total * BUSY_SHARE)
    busy = [h for h in range(24) if profile[h] >= threshold]
    if not busy:
        return None

    current = now.hour
    is_busy = current in busy

    # 지금부터 24시간을 훑어 상태가 바뀌는 첫 시각을 찾는다
    change_hour = None
    for step in range(1, 25):
        hour = (current + step) % 24
        if (hour in busy) != is_busy:
            change_hour = hour
            break

    return {
        "total": total,
        "now_hour": current,
        "now_count": int(profile[current]),
        "now_share": float(profile[current]) / total,
        "is_busy": is_busy,
        "busy_hours": busy,
        "peak_hour": int(profile.idxmax()),
        "peak_count": int(profile.max()),
        "change_hour": change_hour,
        "hours_until_change": None if change_hour is None else (change_hour - current) % 24,
    }


# ---------------------------------------------------------------------------
# 구역 시각화 (격자 밀집도 -> 카카오맵 Polygon)
# ---------------------------------------------------------------------------
# 밀집도 단계별 (채우기 색, 투명도). 뒤로 갈수록 진하다.
GRID_LEVELS = [
    ("#ffd166", 0.25),  # 낮음
    ("#f4a261", 0.35),
    ("#e76f51", 0.45),
    ("#e63946", 0.55),  # 높음
]

METRES_PER_DEGREE = 111_320


def build_density_grid(
    points: pd.DataFrame,
    cell_m: int = 150,
    min_count: int = 1,
    top_ratio: float | None = None,
    weight_col: str | None = None,
) -> list[dict]:
    """점 데이터를 격자로 묶어 카카오맵 Polygon 입력 목록으로 만든다.

    단속 이력은 주소 단위 '점'이라 행정구역 경계가 없다. 행정동으로 칠하면
    다발구역(보통 한 블록 규모)이 뭉개지므로, cell_m 크기의 정사각 격자로 묶어
    칸마다 건수를 세고 그 값에 따라 색을 진하게 칠한다.

    weight_col 을 주면 그 컬럼을 합산하고(예: 주소별 단속 건수),
    없으면 격자 안의 점 개수를 센다.
    min_count 미만인 칸은 버린다 (한두 건까지 칠하면 지도가 온통 색이 된다).
    top_ratio(0~1)를 주면 건수 상위 그 비율의 칸만 남긴다. 데이터 양이 늘어도
    표시되는 칸 수가 일정하게 유지되므로 "최소 몇 건" 보다 다루기 쉽다.
    """
    usable = points.dropna(subset=["latitude", "longitude"])
    if usable.empty:
        return []

    lat = pd.to_numeric(usable["latitude"], errors="coerce").to_numpy(dtype=float)
    lng = pd.to_numeric(usable["longitude"], errors="coerce").to_numpy(dtype=float)
    ok = np.isfinite(lat) & np.isfinite(lng)
    lat, lng = lat[ok], lng[ok]
    if lat.size == 0:
        return []

    if weight_col and weight_col in usable.columns:
        weights = pd.to_numeric(usable[weight_col], errors="coerce").fillna(1).to_numpy(dtype=float)[ok]
    else:
        weights = np.ones(lat.size)

    # 위도 1도는 어디서나 약 111km지만, 경도 1도는 위도에 따라 짧아진다.
    d_lat = cell_m / METRES_PER_DEGREE
    d_lng = cell_m / (METRES_PER_DEGREE * np.cos(np.radians(float(lat.mean()))))

    lat0, lng0 = lat.min(), lng.min()
    row = np.floor((lat - lat0) / d_lat).astype(int)
    col = np.floor((lng - lng0) / d_lng).astype(int)

    cells = (
        pd.DataFrame({"row": row, "col": col, "weight": weights})
        .groupby(["row", "col"], as_index=False)["weight"]
        .sum()
    )
    if top_ratio is not None and 0 < top_ratio < 1:
        cells = cells[cells["weight"] >= cells["weight"].quantile(1 - top_ratio)]
    cells = cells[cells["weight"] >= min_count]
    if cells.empty:
        return []

    # 최대값 대비 비율로 4단계 색을 매긴다
    top = float(cells["weight"].max())
    polygons = []
    for _, cell in cells.iterrows():
        south = lat0 + cell["row"] * d_lat
        west = lng0 + cell["col"] * d_lng
        north, east = south + d_lat, west + d_lng

        ratio = float(cell["weight"]) / top if top else 0.0
        step = min(int(ratio * len(GRID_LEVELS)), len(GRID_LEVELS) - 1)
        color, opacity = GRID_LEVELS[step]

        polygons.append(
            {
                "path": [[south, west], [south, east], [north, east], [north, west]],
                "color": color,
                "opacity": opacity,
                "name": f"{cell_m}m 격자",
                "info": f"이 구역 누적 {cell['weight']:,.0f}건",
            }
        )
    return polygons


def nearest_parking(lat: float, lng: float, lots: pd.DataFrame, limit: int = 3) -> pd.DataFrame:
    """가장 가까운 합법 주차장 N곳 (위험 구역일 때 대안으로 제시)."""
    usable = lots.dropna(subset=["latitude", "longitude"])
    if usable.empty:
        return usable

    out = usable.copy()
    out["distance_m"] = distances_m(lat, lng, usable)
    return out.nsmallest(limit, "distance_m")

# ---------------------------------------------------------------------------
# 과태료 안내
# ---------------------------------------------------------------------------
# 도로교통법 시행령 기준 불법주정차 과태료(승용차). 지자체·구역별로 달라질 수 있어
# 화면에서는 반드시 "참고 금액"으로 표시한다.
FINE_TABLE = [
    ("일반 구역", 40_000, "일반 도로의 주정차 금지 구역"),
    ("절대 금지 구역", 80_000, "소화전·교차로·버스정류소·횡단보도 주변"),
    ("어린이 보호구역", 120_000, "초등학교 등 스쿨존 (08~20시)"),
]


def expected_fine(level: str) -> dict:
    """판정 등급에 맞춰 보여줄 과태료 안내.

    금액을 겁주려고 쓰는 게 아니라, "여기 세우면 이만큼 든다"를 먼저 보여줘서
    합법 주차장 요금과 비교되게 하려는 것이다.
    """
    base = FINE_TABLE[0][1]
    return {
        "amount": base,
        "table": FINE_TABLE,
        "note": "승용차 기준 참고 금액입니다. 구역·차종·지자체에 따라 달라집니다.",
        "show": level in ("위험", "주의"),
    }
