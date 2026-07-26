"""
[담당: 승희] 민영 · 부설 주차장 수집기.

처음에는 주차장 예약 사이트를 크롤링할 계획이었지만, 확인해보니
    - 대부분 로그인/JS 렌더링이 필요하고 (Selenium 상시 구동 부담)
    - 이용약관에서 자동 수집을 금지하는 곳이 많다
그래서 **행정안전부 전국주차장정보표준데이터**(공공데이터, 재배포 허용)를
민영·부설 소스로 쓴다. 수집 자체는 collectors/standard_parking_api.py 가 하고,
이 파일은 거기서 민영·부설만 골라내 DB 적재용 CSV로 떨어뜨리는 역할을 한다.

실행
    # 표준데이터 CSV를 data/raw/national_parking.csv 에 받아둔 뒤
    uv run python collectors/private_parking_crawler.py --district 종로구
    # 또는 .env 에 DATA_GO_KR_API_KEY 를 넣고
    uv run python collectors/private_parking_crawler.py --district 종로구 --api
    -> data/cleaned/private_parking.csv 생성

TODO(승희): 거주자우선주차 실시간 공유 정보(park.ijongno.co.kr)는 Selenium이
필요해서 아직 미구현. 확보되면 source="crawl" 로 여기에 합치면 된다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collectors import standard_parking_api  # noqa: E402
from collectors.merge_parking import to_table_schema  # noqa: E402

DEFAULT_OUTPUT = ROOT / "data/cleaned/private_parking.csv"

# 이용자 입장에서 '공영이 아닌 곳'은 전부 민영 취급한다 (부설 = 건물 부설주차장)
PRIVATE_CATEGORIES = ("민영", "부설")


def collect(district: str | None = None, use_api: bool = False) -> pd.DataFrame:
    """표준데이터에서 민영·부설 주차장만 골라 통합 스키마로 반환."""
    standard = standard_parking_api.collect(district=district, use_api=use_api)
    if standard.empty:
        return to_table_schema(pd.DataFrame())

    is_private = (
        standard["lot_category"].isin(PRIVATE_CATEGORIES)
        | standard.get("lot_type", pd.Series("", index=standard.index)).eq("부설")
    )
    private = standard.loc[is_private].copy()

    # 부설주차장은 구분이 비어 오는 경우가 있어 '민영'으로 통일해둔다
    private["lot_category"] = private["lot_category"].where(
        private["lot_category"].isin(PRIVATE_CATEGORIES), "민영"
    )
    return to_table_schema(private)


def main() -> None:
    parser = argparse.ArgumentParser(description="민영·부설 주차장 수집 (표준데이터 기반)")
    parser.add_argument("--district", help="자치구명 필터 (예: 종로구)")
    parser.add_argument("--api", action="store_true", help="CSV 대신 오픈 API로 수집")
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT), help="저장 경로")
    args = parser.parse_args()

    try:
        result = collect(district=args.district, use_api=args.api)
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"⚠ 민영주차장 수집 실패\n{exc}")
        raise SystemExit(1) from exc

    print(f"민영·부설 주차장: {len(result):,}곳")
    if not result.empty:
        print(result["lot_type"].value_counts(dropna=False).to_string())

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"저장 완료 -> {out_path}")


if __name__ == "__main__":
    main()
