# -*- coding: utf-8 -*-
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

동작:
  1) data/raw/ 에 내려받은 분기별 CSV 여러 개를 한 번에 읽어 병합
  2) ERD의 ENFORCEMENT_HISTORY 스키마(address, enforced_at, latitude, longitude)에
     맞춰 정제하고 data/cleaned/ 에 저장
  3) --load-db 옵션을 주면 common/db.py를 통해 MySQL ENFORCEMENT_HISTORY 테이블에 적재
  4) 다발구역/시간대/요일 집계 CSV도 함께 생성

연동: pages/1_단속_다발구역.py 에서 이 모듈의 extract_dong(), aggregate_* 함수를 재사용합니다.

사용법:
    # data/raw/ 안의 분기별 CSV(예: 종로구_단속현황_2024Q1.csv 등)를 전부 병합해 정제
    uv run python collectors/enforcement_history.py --input "data/raw/*.csv"

    # 따옴표 없이 넘겨도 동작 (쉘이 먼저 확장해서 여러 파일명이 --input 뒤에 나열되는 경우 포함)
    uv run python collectors/enforcement_history.py --input data/raw/*.csv

    # 특정 파일 하나만
    uv run python collectors/enforcement_history.py --input data/raw/종로구_단속현황_2024Q1.csv

    # 폴더 + 특정 파일을 함께 지정하는 것도 가능
    uv run python collectors/enforcement_history.py --input data/raw/ data/raw_extra/late_2025.csv

    # 정제 + MySQL ENFORCEMENT_HISTORY 테이블 적재
    uv run python collectors/enforcement_history.py --input "data/raw/*.csv" --load-db
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

# 프로젝트 루트를 import 경로에 추가 (common.db 를 쓰기 위함)
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))


# --------------------------------------------------------------------------
# 1. 원본 컬럼명 자동 매핑
#    공공데이터포털/서울열린데이터광장 제공 파일은 연도/기관별로 컬럼명이 조금씩 다릅니다.
# --------------------------------------------------------------------------
COLUMN_CANDIDATES = {
    # OA-22190 실제 컬럼명(단속주소, 단속일시)을 최우선으로 두고,
    # 다른 연도/기관 파일과의 호환을 위해 유사 이름도 후보로 남겨둠.
    "address": ["단속주소", "단속장소", "위반장소", "단속위치", "주소", "소재지", "address"],
    "enforced_at": ["단속일시", "단속일자", "단속날짜", "일시", "date", "datetime"],
    "lat": ["위도", "lat", "latitude", "y좌표"],
    "lon": ["경도", "lon", "lng", "longitude", "x좌표"],
}


def find_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    cols = list(df.columns)
    for cand in candidates:
        for col in cols:
            if str(col).strip() == cand:
                return col
    for cand in candidates:
        for col in cols:
            if cand in str(col):
                return col
    return None


def _read_one(p: Path) -> pd.DataFrame:
    if p.suffix.lower() in [".xlsx", ".xls"]:
        return pd.read_excel(p)
    for enc in ["cp949", "utf-8", "utf-8-sig"]:
        try:
            return pd.read_csv(p, encoding=enc)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"CSV 인코딩을 확인해주세요 (cp949 / utf-8 모두 실패): {p}")


def resolve_input_files(input_specs: list[str]) -> list[Path]:
    """--input 값(들)을 실제 파일 목록으로 해석.

    input_specs 각 항목은 다음 형태를 지원:
      - 단일 파일 경로:            data/raw/2024Q1.csv
      - glob 패턴(따옴표 권장):     "data/raw/*.csv"
      - 디렉토리:                  data/raw/  (내부 csv/xlsx 전부)

    nargs='+' 로 여러 값을 받기 때문에, 따옴표 없이 glob을 넘겨 쉘이
    미리 확장해버린 경우(예: --input data/raw/*.csv 가 여러 파일명으로 쪼개져 들어옴)에도
    각 파일명이 그대로 input_specs 원소가 되어 정상 처리됩니다.
    """
    files: list[Path] = []
    for spec in input_specs:
        p = Path(spec)
        if p.is_dir():
            found = sorted(list(p.glob("*.csv")) + list(p.glob("*.xlsx")) + list(p.glob("*.xls")))
        elif any(ch in spec for ch in "*?[]"):
            found = sorted(Path().glob(spec))
        elif p.exists():
            found = [p]
        else:
            found = []

        if not found:
            raise FileNotFoundError(
                f"입력에 해당하는 파일을 찾지 못했습니다: {spec}. "
                "data/raw/ 폴더에 서울 열린데이터광장(OA-22190)에서 내려받은 "
                "분기별 CSV를 넣었는지 확인해주세요."
            )
        files.extend(found)

    # 같은 파일이 여러 spec에 걸쳐 중복으로 잡힐 수 있어 경로 기준으로 중복 제거 (순서 유지)
    seen = set()
    unique_files = []
    for f in files:
        rp = f.resolve()
        if rp not in seen:
            seen.add(rp)
            unique_files.append(f)
    return unique_files


def load_raw(input_specs: list[str]) -> pd.DataFrame:
    """단일/여러 분기 CSV를 모두 읽어 하나의 DataFrame으로 병합."""
    files = resolve_input_files(input_specs)
    frames = []
    for f in files:
        df = _read_one(f)
        df["_source_file"] = f.name  # 디버깅/추적용, 정제 단계에서 제거됨
        frames.append(df)
        print(f"  - {f.name}: {len(df):,}행")

    merged = pd.concat(frames, ignore_index=True, sort=False)
    return merged


# --------------------------------------------------------------------------
# 2. 정제: ERD(ENFORCEMENT_HISTORY) 스키마로 맞추기
#    -> address, enforced_at, latitude, longitude 4개 컬럼만 남김 (history_id는 AUTO_INCREMENT)
# --------------------------------------------------------------------------
def clean_to_schema(df_raw: pd.DataFrame, district_filter: str = "종로구") -> pd.DataFrame:
    colmap = {key: find_column(df_raw, cands) for key, cands in COLUMN_CANDIDATES.items()}
    missing = [k for k, v in colmap.items() if v is None and k in ("address", "enforced_at")]
    if missing:
        raise KeyError(
            f"필수 컬럼을 찾지 못했습니다: {missing}. "
            f"원본 컬럼: {list(df_raw.columns)} / COLUMN_CANDIDATES를 조정해주세요."
        )

    df = pd.DataFrame()
    df["address"] = df_raw[colmap["address"]].astype(str).str.strip()
    df["enforced_at"] = pd.to_datetime(df_raw[colmap["enforced_at"]], errors="coerce")
    df["latitude"] = pd.to_numeric(df_raw[colmap["lat"]], errors="coerce") if colmap["lat"] else pd.NA
    df["longitude"] = pd.to_numeric(df_raw[colmap["lon"]], errors="coerce") if colmap["lon"] else pd.NA

    # 필수값 결측 제거
    df = df.dropna(subset=["address", "enforced_at"])

    # 분기별 CSV를 병합하면서 경계 구간이 겹쳐 들어왔을 수 있어 완전 중복 행 제거
    before = len(df)
    df = df.drop_duplicates(subset=["address", "enforced_at", "latitude", "longitude"])
    if before != len(df):
        print(f"  - 중복 제거: {before:,} -> {len(df):,}행")

    # 종로구만 필터링 (전체 서울 데이터를 넣은 경우 대비)
    if district_filter:
        df = df[df["address"].str.contains(district_filter, na=False)]

    df = df.reset_index(drop=True)
    return df


# --------------------------------------------------------------------------
# 3. 파생 필드 (동 추출, 시/요일) - DB에는 저장하지 않고 집계/화면 표시용으로만 사용
# --------------------------------------------------------------------------
def extract_dong(address: str) -> str | None:
    """주소 문자열에서 'OO동'을 추출. 없으면 None."""
    if not isinstance(address, str):
        return None
    m = re.search(r"([가-힣0-9]+동)", address)
    return m.group(1) if m else None


def with_derived_fields(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["dong"] = df["address"].apply(extract_dong)
    df["hour"] = df["enforced_at"].dt.hour
    weekday_kor = {0: "월", 1: "화", 2: "수", 3: "목", 4: "금", 5: "토", 6: "일"}
    df["weekday"] = df["enforced_at"].dt.weekday.map(weekday_kor)
    return df


# --------------------------------------------------------------------------
# 4. 집계 (다발구역 / 시간대 / 요일) - Streamlit 페이지에서도 동일 함수를 재사용
# --------------------------------------------------------------------------
def aggregate_hotspots(df: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
    df = with_derived_fields(df) if "dong" not in df.columns else df
    counts = df["dong"].value_counts(dropna=True).head(top_n).reset_index()
    counts.columns = ["구역(동)", "단속건수"]
    return counts


def aggregate_by_hour(df: pd.DataFrame) -> pd.DataFrame:
    df = with_derived_fields(df) if "hour" not in df.columns else df
    counts = df["hour"].value_counts().sort_index().reset_index()
    counts.columns = ["시간대", "단속건수"]
    return counts


def aggregate_by_weekday(df: pd.DataFrame) -> pd.DataFrame:
    df = with_derived_fields(df) if "weekday" not in df.columns else df
    order = ["월", "화", "수", "목", "금", "토", "일"]
    counts = df["weekday"].value_counts().reindex(order).fillna(0).astype(int).reset_index()
    counts.columns = ["요일", "단속건수"]
    return counts


# --------------------------------------------------------------------------
# 5. DB 적재
# --------------------------------------------------------------------------
def load_to_db(df_schema: pd.DataFrame) -> int:
    """ERD 스키마(address, enforced_at, latitude, longitude)만 ENFORCEMENT_HISTORY에 적재."""
    from common.db import bulk_insert_df  # 지연 import: DB 미사용 시 sqlalchemy 의존성 불필요

    cols = ["address", "enforced_at", "latitude", "longitude"]
    return bulk_insert_df(df_schema[cols], table_name="ENFORCEMENT_HISTORY", if_exists="append")


# --------------------------------------------------------------------------
# 6. 메인 (CLI)
# --------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="종로구 불법주정차 단속이력 정제/집계/적재")
    parser.add_argument(
        "--input", "-i", required=True, nargs="+",
        help=(
            '원본 CSV/XLSX 경로. 단일 파일, glob 패턴("data/raw/*.csv"), 폴더 경로, '
            "또는 이들을 공백으로 나열한 여러 개를 지원합니다. "
            "(따옴표 없이 glob을 넘겨 쉘이 먼저 확장하는 경우에도 정상 동작하도록 nargs='+' 사용)"
        ),
    )
    parser.add_argument("--output-dir", "-o", default=str(ROOT_DIR / "data" / "cleaned"))
    parser.add_argument("--district", default="종로구", help="필터링할 자치구명")
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--load-db", action="store_true", help="정제 후 MySQL ENFORCEMENT_HISTORY에 적재")
    args = parser.parse_args()

    print(f"[1/4] 원본 로딩: {args.input}")
    df_raw = load_raw(args.input)
    print(f"  -> 병합 후 총 {len(df_raw):,}행")

    print(f"[2/4] 정제 (ERD 스키마 매핑, 지역 필터: {args.district})")
    df_schema = clean_to_schema(df_raw, district_filter=args.district)
    print(f"  -> 정제 후 {len(df_schema):,}행")

    if df_schema.empty:
        print("경고: 정제 후 데이터가 없습니다. --district 옵션이나 원본 데이터를 확인하세요.")
        return

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cleaned_path = out_dir / "enforcement_history_cleaned.csv"
    df_schema.to_csv(cleaned_path, index=False, encoding="utf-8-sig")
    print(f"  -> 정제 CSV 저장: {cleaned_path}")

    print("[3/4] 다발구역/시간대/요일 집계 (참고용)")
    df_derived = with_derived_fields(df_schema)
    hotspots = aggregate_hotspots(df_derived, top_n=args.top_n)
    by_hour = aggregate_by_hour(df_derived)
    by_weekday = aggregate_by_weekday(df_derived)

    hotspots.to_csv(out_dir / "hotspots_top_n.csv", index=False, encoding="utf-8-sig")
    by_hour.to_csv(out_dir / "by_hour.csv", index=False, encoding="utf-8-sig")
    by_weekday.to_csv(out_dir / "by_weekday.csv", index=False, encoding="utf-8-sig")

    print("\n[단속 다발구역 TOP N]")
    print(hotspots.to_string(index=False))

    print("\n[4/4] DB 적재")
    if args.load_db:
        try:
            n = load_to_db(df_schema)
            print(f"  -> ENFORCEMENT_HISTORY 테이블에 {n:,}행 적재 완료")
        except Exception as e:
            print(f"  -> DB 적재 실패: {e}")
            print("     common/db.py의 DB_CONFIG(.env: MYSQL_HOST/PORT/USER/PASSWORD/DATABASE)를 확인하세요.")
    else:
        print("  -> --load-db 옵션이 없어 DB 적재를 건너뜁니다. (CSV만 저장됨)")

    print(f"\n완료! 결과는 '{out_dir}' 에 저장되었습니다.")


if __name__ == "__main__":
    main()