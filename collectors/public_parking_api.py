"""
[담당: 승희] 서울시 공영주차장 안내 정보(OA-13122) 수집 · 정제.

원본 데이터 특징
- 인코딩이 EUC-KR(CP949)이라 그냥 read_csv 하면 한글이 깨진다.
- '구' 컬럼이 따로 없고 '주소' 안에 "종로구 ..." 형태로 들어있다.
- 노상 주차구역은 하나의 주차장코드가 여러 좌표점(행)으로 쪼개져 있다.
  그대로 지도에 찍으면 같은 주차장에 마커가 수십 개 생기므로
  주차장코드로 묶고 좌표는 평균(중심점)을 쓴다. (2,189행 -> 850곳)
- 좌표가 0.0 이거나 비어있는 행이 꽤 많다. 0.0은 "정보 없음"이므로 결측 처리한다.

실행
    # 서울 전체
    uv run python collectors/public_parking_api.py
    # 특정 자치구만
    uv run python collectors/public_parking_api.py --district 종로구
    -> data/cleaned/public_parking.csv 생성

데이터 출처
    https://data.seoul.go.kr/dataList/OA-13122/S/1/datasetView.do
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

# 원본 CSV를 찾을 위치 (앞에 있는 것부터 사용)
RAW_CANDIDATES = (
    ROOT / "data/raw/seoul_parking.csv",
    ROOT / "seoul_parking.csv",
    ROOT / "data/raw/서울시 공영주차장 안내 정보.csv",
)
DEFAULT_OUTPUT = ROOT / "data/cleaned/public_parking.csv"

ADDRESS_COL = "주소"
ID_COL = "주차장코드"
COORD_COLS = ["위도", "경도"]

# 한글 원본 컬럼 -> 통합 테이블 컬럼 (collectors/merge_parking.py의 TABLE_COLUMNS와 동일 규약)
COLUMN_MAP = {
    "주차장코드": "parking_id",
    "주차장명": "parking_name",
    "주소": "address",
    "주차장 종류명": "lot_type",
    "운영구분명": "operation_rule",
    "전화번호": "phone",
    "총 주차면": "capacity",
    "유무료구분명": "pay_type",
    "야간무료개방여부명": "night_free",
    "평일 운영 시작시각(HHMM)": "weekday_start",
    "평일 운영 종료시각(HHMM)": "weekday_end",
    "주말 운영 시작시각(HHMM)": "weekend_start",
    "주말 운영 종료시각(HHMM)": "weekend_end",
    "공휴일 운영 시작시각(HHMM)": "holiday_start",
    "공휴일 운영 종료시각(HHMM)": "holiday_end",
    "월 정기권 금액": "monthly_fee",
    "기본 주차 요금": "base_fee",
    "기본 주차 시간(분 단위)": "base_time",
    "추가 단위 요금": "add_fee",
    "추가 단위 시간(분 단위)": "add_time",
    "일 최대 요금": "day_max_fee",
    "위도": "latitude",
    "경도": "longitude",
}

# 결측 허용 정수형(Int64)으로 바꿀 컬럼 - 요금/시간은 소수점이 의미 없다
INT_COLUMNS = [
    "capacity", "monthly_fee", "base_fee", "base_time", "add_fee", "add_time",
    "day_max_fee", "weekday_start", "weekday_end", "weekend_start", "weekend_end",
    "holiday_start", "holiday_end",
]


# ---------------------------------------------------------------------------
# 1) 원본 읽기
# ---------------------------------------------------------------------------
def find_raw_file() -> Path:
    """저장소 안에서 원본 CSV를 찾는다. 없으면 안내 메시지와 함께 에러."""
    for path in RAW_CANDIDATES:
        if path.exists():
            return path
    tried = "\n  ".join(str(p) for p in RAW_CANDIDATES)
    raise FileNotFoundError(
        "서울시 공영주차장 CSV를 찾지 못했습니다. 아래 경로 중 하나에 저장해주세요:\n  "
        f"{tried}\n"
        "다운로드: https://data.seoul.go.kr/dataList/OA-13122/S/1/datasetView.do"
    )


def load_raw(path: str | Path | None = None) -> pd.DataFrame:
    """원본 CSV를 인코딩 자동 판별로 읽는다.

    공공데이터 CSV는 EUC-KR이 기본이지만, 한 번 정제해서 utf-8-sig로 저장한
    파일(종로구_공영주차장_정제.csv 등)도 그대로 읽을 수 있게 여러 인코딩을 시도한다.
    """
    path = Path(path) if path else find_raw_file()
    if not path.exists():
        # 노트북 등에서 data/raw/ 경로를 넘겼는데 파일이 저장소 루트에 있는 경우 구제
        path = find_raw_file()

    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            df = pd.read_csv(path, encoding=encoding)
        except (UnicodeDecodeError, LookupError) as exc:
            last_error = exc
            continue
        # 인코딩이 틀리면 컬럼명이 깨져서 '주차장코드'가 안 잡힌다
        if ID_COL in df.columns:
            return df
        last_error = ValueError(f"{encoding}로 읽었으나 '{ID_COL}' 컬럼이 없음")

    raise ValueError(f"{path} 를 읽지 못했습니다: {last_error}")


def filter_district(df: pd.DataFrame, keyword: str) -> pd.DataFrame:
    """주소에 자치구명(예: '종로구')이 포함된 행만 남긴다."""
    mask = df[ADDRESS_COL].astype(str).str.contains(keyword, na=False)
    return df.loc[mask].copy()


# ---------------------------------------------------------------------------
# 2) 노상주차장 좌표 중복 병합 (핵심 처리)
# ---------------------------------------------------------------------------
def dedupe_by_parking_lot(df: pd.DataFrame) -> pd.DataFrame:
    """같은 주차장코드로 흩어진 여러 좌표점 행을 1행으로 합친다.

    - 위도/경도: 평균 (해당 구역의 중심 좌표)
    - 나머지 컬럼: 그룹 안에서 값이 동일하므로 첫 값 사용

    0.0 좌표는 "정보 없음"이라 평균에 섞이면 중심점이 바다로 가버린다.
    평균을 내기 전에 결측으로 바꿔서 제외한다.
    """
    if df.empty:
        return df.copy()

    work = df.copy()
    for col in COORD_COLS:
        work[col] = pd.to_numeric(work[col], errors="coerce").replace(0.0, pd.NA)

    other_cols = [c for c in work.columns if c not in COORD_COLS]
    agg = {col: "mean" for col in COORD_COLS}
    agg.update({col: "first" for col in other_cols if col != ID_COL})

    result = work.groupby(ID_COL, as_index=False).agg(agg)
    return result[df.columns]  # 원래 컬럼 순서 유지


# ---------------------------------------------------------------------------
# 3) 통합 테이블 스키마로 변환
# ---------------------------------------------------------------------------
def _district_of(address: pd.Series) -> pd.Series:
    """주소 문자열에서 자치구명을 뽑는다 ('종로구 세종로 80-1' -> '종로구')."""
    return address.astype(str).str.extract(r"(?:^|\s)([가-힣]+구)(?=\s|$)", expand=False)


def to_table_schema(df: pd.DataFrame) -> pd.DataFrame:
    """한글 컬럼 원본을 통합 테이블 스키마(영문 컬럼 + 숫자 타입)로 변환."""
    out = df.rename(columns=COLUMN_MAP)
    out = out[[c for c in COLUMN_MAP.values() if c in out.columns]].copy()

    # 좌표: 0.0은 '정보 없음'
    for col in ("latitude", "longitude"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").replace(0.0, pd.NA)

    # 요금/시간: 결측 허용 정수형
    for col in INT_COLUMNS:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").round().astype("Int64")

    out["parking_id"] = out["parking_id"].astype(str).str.strip()
    out["parking_name"] = out["parking_name"].astype(str).str.strip()
    out["district"] = _district_of(out["address"])

    # '노외 주차장' -> '노외' 처럼 짧게 (표준데이터의 주차장유형과 표기를 맞춘다)
    if "lot_type" in out.columns:
        out["lot_type"] = out["lot_type"].astype(str).str.replace(" 주차장", "", regex=False)

    out["lot_category"] = "공영"
    out["source"] = "seoul_public"
    return out.reset_index(drop=True)


# ---------------------------------------------------------------------------
# 4) 전체 파이프라인
# ---------------------------------------------------------------------------
def collect(path: str | Path | None = None, district: str | None = None) -> pd.DataFrame:
    """원본 읽기 -> (자치구 필터) -> 좌표 병합 -> 스키마 변환까지 한 번에."""
    df = load_raw(path)
    if district:
        df = filter_district(df, district)
    df = dedupe_by_parking_lot(df)
    return to_table_schema(df)


def main() -> None:
    parser = argparse.ArgumentParser(description="서울시 공영주차장 CSV 정제")
    parser.add_argument("--csv", help="원본 CSV 경로 (생략 시 자동 탐색)")
    parser.add_argument("--district", help="자치구명 필터 (예: 종로구). 생략 시 서울 전체")
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT), help="저장 경로")
    args = parser.parse_args()

    raw = load_raw(args.csv)
    print(f"원본 전체 행수: {len(raw):,}")

    if args.district:
        raw = filter_district(raw, args.district)
        print(f"{args.district} 필터 후: {len(raw):,}행 (고유 주차장 {raw[ID_COL].nunique():,}곳)")

    merged = dedupe_by_parking_lot(raw)
    print(f"좌표 병합 후: {len(merged):,}행 (주차장당 1행)")

    result = to_table_schema(merged)
    no_coord = result[["latitude", "longitude"]].isna().any(axis=1).sum()
    print(f"좌표 없음: {no_coord:,}곳 -> 지도 표시 가능 {len(result) - no_coord:,}곳")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"저장 완료 -> {out_path}")


if __name__ == "__main__":
    main()
