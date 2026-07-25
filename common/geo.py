"""
위치 관련 공통 유틸: 주소 <-> 좌표 변환(Geocoding), 거리 계산.
"""

import math

import requests


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """두 좌표 사이의 직선거리(km)를 하버사인 공식으로 계산."""
    r = 6371.0  # 지구 반지름(km)
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def geocode_address(address: str, kakao_rest_key: str) -> tuple[float, float] | None:
    """카카오 로컬(주소 검색) API로 주소 -> (위도, 경도) 변환.

    ⚠ REST API 키 사용 (지도 표시용 JavaScript 키와 다름).
    """
    url = "https://dapi.kakao.com/v2/local/search/address.json"
    headers = {"Authorization": f"KakaoAK {kakao_rest_key}"}
    res = requests.get(url, headers=headers, params={"query": address}, timeout=5)
    res.raise_for_status()
    docs = res.json().get("documents", [])
    if not docs:
        return None
    return float(docs[0]["y"]), float(docs[0]["x"])  # (위도, 경도)


def filter_within_radius(df, center_lat: float, center_lng: float, radius_km: float, lat_col="lat", lng_col="lng"):
    """DataFrame에서 중심 좌표 반경(km) 이내 행만 필터링."""
    if df.empty:
        return df
    distances = df.apply(
        lambda row: haversine_km(center_lat, center_lng, row[lat_col], row[lng_col]), axis=1
    )
    return df.assign(distance_km=distances).loc[distances <= radius_km].sort_values("distance_km")