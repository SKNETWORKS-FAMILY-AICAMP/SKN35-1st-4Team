"""
[담당: A 또는 D] 서울시 불법주정차 단속 정보 정제 (data.seoul.go.kr, OA-22190).

데이터셋 페이지: https://data.seoul.go.kr/dataList/OA-22190/F/1/datasetView.do
(실제로 열어서 확인함: 2021.9.29~2025.12.31 기간을 분기별로 나눈 CSV 12개를
"파일내려받기" 방식으로 제공한다. 다운로드 버튼이 javascript:downloadFile('15')
같은 JS 트리거라 자동화가 번거롭다 -> 공영주차장 CSV 때와 동일하게, 팀원이 필요한
분기 CSV를 브라우저에서 직접 내려받아 data/raw/에 넣고 이 스크립트로 정제하는
흐름을 권장한다.)

컬럼(데이터셋 설명 기준): 단속일시, 단속주소, 위도, 경도

이 파일은 정제뿐 아니라 "다발구역"(단속이 자주 발생하는 주소) TOP N 집계도
같이 만들어준다 - 팀원이 언급한 "다발구역/견인/이의신청" 분류 중 다발구역에
해당하는 실제 데이터 기반 기능.
"""

from pathlib import Path

import pandas as pd

COLUMN_MAP = {
    "단속일시": "enforced_at",
    "단속주소": "address",
    "위도": "latitude",
    "경도": "longitude",
}


def load_raw(csv_path: str) -> pd.DataFrame:
    """서울 열린데이터광장 CSV는 EUC-KR인 경우가 많아 우선 시도하고, 실패하면 UTF-8로 재시도."""
    try:
        return pd.read_csv(csv_path, encoding="euc-kr")
    except UnicodeDecodeError:
        return pd.read_csv(csv_path, encoding="utf-8")


def to_enforcement_history(raw: pd.DataFrame) -> pd.DataFrame:
    """ENFORCEMENT_HISTORY 테이블 스키마로 컬럼 정리."""
    df = raw.rename(columns=COLUMN_MAP)
    keep = ["address", "enforced_at", "latitude", "longitude"]
    return df[[c for c in keep if c in df.columns]]


def filter_district(df: pd.DataFrame, keyword: str, address_col: str = "address") -> pd.DataFrame:
    mask = df[address_col].astype(str).str.contains(keyword, na=False)
    return df.loc[mask].copy()


def build_hotspot_ranking(df: pd.DataFrame, top_n: int = 20) -> pd.DataFrame:
    """주소별 단속 건수를 집계해 다발구역 TOP N을 뽑는다.

    좌표는 같은 주소로 묶인 건들의 평균(대표 좌표)을 사용해 지도에 한 점으로 표시할 수 있게 한다.
    """
    valid = df.dropna(subset=["address"])
    ranking = (
        valid.groupby("address", as_index=False)
        .agg(
            violation_count=("address", "size"),
            latitude=("latitude", "mean"),
            longitude=("longitude", "mean"),
        )
        .sort_values("violation_count", ascending=False)
        .head(top_n)
        .reset_index(drop=True)
    )
    return ranking


def main(
    input_csv: str = "data/raw/불법주정차단속_위치정보.csv",
    district_keyword: str | None = "종로구",
) -> None:
    raw = load_raw(input_csv)
    print(f"원본 행수: {len(raw):,}")

    cleaned = to_enforcement_history(raw)

    if district_keyword:
        cleaned = filter_district(cleaned, district_keyword)
        print(f"'{district_keyword}' 필터링 후 행수: {len(cleaned):,}")

    Path("data/cleaned").mkdir(parents=True, exist_ok=True)

    cleaned.to_csv("data/cleaned/enforcement_history.csv", index=False, encoding="utf-8-sig")
    print("data/cleaned/enforcement_history.csv 저장 완료")

    hotspots = build_hotspot_ranking(cleaned)
    hotspots.to_csv("data/cleaned/enforcement_hotspot_top20.csv", index=False, encoding="utf-8-sig")
    print(f"data/cleaned/enforcement_hotspot_top20.csv 저장 완료 (다발구역 TOP{len(hotspots)})")


if __name__ == "__main__":
    main()