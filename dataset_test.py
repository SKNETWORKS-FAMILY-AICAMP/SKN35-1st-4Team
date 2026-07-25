"""
서울시 공영주차장 안내 정보.csv 에서 종로구 데이터만 뽑아 정제하는 스크립트.

원본 데이터 특징
- 인코딩: EUC-KR (서울 열린데이터광장/공공데이터포털 CSV 대부분 이 인코딩)
- '구' 컬럼이 따로 없고 '주소' 컬럼 안에 "종로구 ..." 형태로 들어있음
- 노상 주차구역은 하나의 주차장코드가 여러 좌표점(위도/경도)으로 나뉘어
  여러 행에 걸쳐 중복 등장함 (같은 코드인데 위도/경도만 조금씩 다름).
  -> 지도에 마커 하나로 찍으려면 주차장코드 기준으로 1행으로 합쳐야 함.
  -> 좌표는 해당 구역 점들의 평균(중심점)으로 계산.

실행
    python3 clean_jongno_parking.py
"""

from pathlib import Path

import pandas as pd

INPUT_FILE = "seoul_parking.csv"
OUTPUT_FILE = "종로구_공영주차장_정제.csv"

# 종로구 매칭에 쓸 컬럼과 키워드
ADDRESS_COL = "주소"
DISTRICT_KEYWORD = "종로구"

# 주차장 하나를 식별하는 키
ID_COL = "주차장코드"

# 여러 좌표점으로 나뉜 행을 합칠 때, 평균을 낼 컬럼(수치형 좌표)과
# 그 외 컬럼은 같은 주차장코드 안에서 값이 동일하므로 첫 값을 사용
COORD_COLS = ["위도", "경도"]


def load_raw(path: str) -> pd.DataFrame:
    return pd.read_csv(path, encoding="euc-kr")


def filter_district(df: pd.DataFrame, keyword: str) -> pd.DataFrame:
    mask = df[ADDRESS_COL].astype(str).str.contains(keyword, na=False)
    return df.loc[mask].copy()


def dedupe_by_parking_lot(df: pd.DataFrame) -> pd.DataFrame:
    """같은 주차장코드로 여러 행(좌표점)이 있으면 1행으로 합친다.

    - 위도/경도: 평균값 (해당 구역의 중심 좌표)
    - 나머지 컬럼: 그룹 내 값이 동일하므로 첫 값 사용
    """
    other_cols = [c for c in df.columns if c not in COORD_COLS]

    agg = {col: "mean" for col in COORD_COLS}
    agg.update({col: "first" for col in other_cols if col != ID_COL})

    result = df.groupby(ID_COL, as_index=False).agg(agg)

    # 원래 컬럼 순서 유지
    return result[df.columns]


def main() -> None:
    raw = load_raw(INPUT_FILE)
    print(f"원본 전체 행수: {len(raw):,}")

    jongno_raw = filter_district(raw, DISTRICT_KEYWORD)
    print(f"종로구 필터링 후 행수 (좌표점 포함): {len(jongno_raw):,}")
    print(f"종로구 고유 주차장 수: {jongno_raw[ID_COL].nunique():,}")

    jongno_clean = dedupe_by_parking_lot(jongno_raw)
    print(f"정제 후 최종 행수 (주차장당 1행): {len(jongno_clean):,}")

    # 좌표가 아예 없는 행 확인 (지도에 못 찍는 데이터)
    missing_coords = jongno_clean[COORD_COLS].isna().any(axis=1).sum()
    if missing_coords:
        print(f"⚠ 위도/경도가 없는 주차장: {missing_coords}건 (지도에는 표시 불가)")

    jongno_clean.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")
    print(f"저장 완료 -> {Path(OUTPUT_FILE).resolve()}")


if __name__ == "__main__":
    main()