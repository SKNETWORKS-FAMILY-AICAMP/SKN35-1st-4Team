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
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# 팀원 스크립트가 저장하는 경로
CCTV_CSV = ROOT / "data/cleaned/cctv_cleaned.csv"
ENFORCEMENT_CSV = ROOT / "data/cleaned/enforcement_history.csv"

# 위험도 판정 기준 (반경 안의 누적 단속 건수 / 가장 가까운 CCTV까지 거리)
DEFAULT_RADIUS_M = 100
DANGER_ENFORCEMENTS = 10
DANGER_CCTV_M = 50
CAUTION_CCTV_M = 150

EMPTY_HOTSPOTS = pd.DataFrame(
    columns=["address", "latitude", "longitude", "violation_count"]
)
EMPTY_CCTV = pd.DataFrame(columns=["address", "latitude", "longitude", "organization"])


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
    """DB가 없거나 테이블이 비어 있으면 None."""
    if not config.is_db_configured():
        return None
    try:
        from common.db import read_sql

        df = read_sql(sql)
    except Exception:  # noqa: BLE001 - DB 미기동/미적재 등 어떤 이유든 CSV로 폴백
        return None
    return df if not df.empty else None


def _read_csv(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
    except (OSError, ValueError):
        return None
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
    return _load_hotspots(_mtime(ENFORCEMENT_CSV))


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

    raw = _read_csv(ENFORCEMENT_CSV)
    if raw is not None and {"address", "latitude", "longitude"} <= set(raw.columns):
        hotspots = (
            raw.dropna(subset=["latitude", "longitude"])
            .groupby("address", as_index=False)
            .agg(
                latitude=("latitude", "mean"),
                longitude=("longitude", "mean"),
                violation_count=("address", "size"),
            )
        )
        return hotspots, f"단속 다발구역: {ENFORCEMENT_CSV.name} ({len(hotspots):,}곳)"

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
        level, message = "위험", "단속이 잦은 구역입니다. 주차를 피하는 편이 좋습니다."
    elif enforcement_count > 0 or (
        nearest_cctv_m is not None and nearest_cctv_m <= CAUTION_CCTV_M
    ):
        level, message = "주의", "단속 이력이나 CCTV가 근처에 있습니다."
    else:
        level, message = "기록 없음", "반경 안에 단속 기록·CCTV가 없습니다. 현장 표지판을 확인하세요."

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
    min_count: int = 2,
    weight_col: str | None = None,
) -> list[dict]:
    """점 데이터를 격자로 묶어 카카오맵 Polygon 입력 목록으로 만든다.

    단속 이력은 주소 단위 '점'이라 행정구역 경계가 없다. 행정동으로 칠하면
    다발구역(보통 한 블록 규모)이 뭉개지므로, cell_m 크기의 정사각 격자로 묶어
    칸마다 건수를 세고 그 값에 따라 색을 진하게 칠한다.

    weight_col 을 주면 그 컬럼을 합산하고(예: 주소별 단속 건수),
    없으면 격자 안의 점 개수를 센다.
    min_count 미만인 칸은 버린다 (한두 건까지 칠하면 지도가 온통 색이 된다).
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