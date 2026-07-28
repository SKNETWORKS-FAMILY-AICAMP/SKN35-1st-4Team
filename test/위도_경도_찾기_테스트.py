import requests

KAKAO_API_KEY = "fd68378de8dbfcdda47c7bca1342bc04"  # .env에 넣어서 관리하세요

import requests

def get_coords(address: str):
    url = "https://dapi.kakao.com/v2/local/search/address.json"
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    params = {"query": address}

    res = requests.get(url, headers=headers, params=params)
    res.raise_for_status()
    data = res.json()

    if not data["documents"]:
        return None, None  # 검색 결과 없음

    doc = data["documents"][0]
    lon = doc["x"]  # 경도
    lat = doc["y"]  # 위도
    return lat, lon

lat, lon = get_coords("서울특별시 강남구 테헤란로 132")
print(lat, lon)