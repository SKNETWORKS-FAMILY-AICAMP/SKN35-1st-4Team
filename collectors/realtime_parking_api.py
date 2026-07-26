"""
[담당: 승희] 서울시 시(市)영주차장 실시간 주차정보(OA-21709) 수집.

공영주차장 안내 정보(OA-13122)에는 "총 주차면"만 있고 지금 몇 자리가 비었는지는 없다.
이 API가 현재 주차 대수(NOW_PRK_VHCL_CNT)를 주기 때문에, 주차장코드로 조인하면
추천 로직의 '여유 점수'를 실제 값으로 계산할 수 있다.

- 대상: 서울시설공단이 관리하는 시영주차장 약 120여 곳 (자치구 주차장은 미포함)
- 인증키: .env 의 SEOUL_OPENAPI_KEY (서울 열린데이터광장에서 무료 발급)
- 키가 없으면 sample 키로 5건만 조회되므로, 키가 없을 때는 빈 결과를 돌려준다.

실행
    uv run python collectors/realtime_parking_api.py
    -> data/cleaned/parking_realtime.csv 생성

데이터 출처
    https://data.seoul.go.kr/dataList/OA-21709/A/1/datasetView.do
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # `python collectors/...` 로 직접 실행해도 config를 찾도록

import config  # noqa: E402

DEFAULT_OUTPUT = ROOT / "data/cleaned/parking_realtime.csv"

BASE_URL = "http://openapi.seoul.go.kr:8088"
SERVICE = "GetParkingInfo"
PAGE_SIZE = 1000  # 서울 열린데이터광장 1회 요청 최대 건수

# API 응답 필드 -> 통합 테이블 컬럼
FIELD_MAP = {
    "PKLT_CD": "parking_id",
    "PKLT_NM": "parking_name",
    "ADDR": "address",
    "TPKCT": "capacity",
    "NOW_PRK_VHCL_CNT": "now_parked",
    "NOW_PRK_VHCL_UPDT_TM": "updated_at",
}


def fetch(service_key: str | None = None, timeout: int = 15) -> pd.DataFrame:
    """실시간 주차정보를 전부 받아 DataFrame으로 반환.

    반환 컬럼: parking_id, parking_name, address, capacity, now_parked,
              available(=capacity-now_parked), updated_at

    인증키가 없거나 API가 오류를 주면 빈 DataFrame을 돌려준다.
    실시간 정보는 '있으면 좋은' 부가 정보라서, 실패해도 검색 기능 자체는 돌아가야 한다.
    """
    service_key = service_key or config.SEOUL_OPENAPI_KEY
    if not service_key:
        return empty_frame()

    rows: list[dict] = []
    start = 1
    while True:
        url = f"{BASE_URL}/{service_key}/json/{SERVICE}/{start}/{start + PAGE_SIZE - 1}/"
        try:
            payload = requests.get(url, timeout=timeout).json()
        except (requests.RequestException, ValueError) as exc:
            raise RuntimeError(f"실시간 주차정보 API 호출 실패: {exc}") from exc

        body = payload.get(SERVICE)
        if body is None:
            # 인증키 오류 등은 최상위 RESULT로 온다
            result = payload.get("RESULT", {})
            raise RuntimeError(
                f"실시간 주차정보 API 오류: {result.get('CODE')} {result.get('MESSAGE')}"
            )

        page_rows = body.get("row", [])
        rows.extend(page_rows)

        total = int(body.get("list_total_count", len(rows)))
        start += PAGE_SIZE
        if start > total or not page_rows:
            break

    if not rows:
        return empty_frame()

    df = pd.DataFrame(rows)
    df = df[[c for c in FIELD_MAP if c in df.columns]].rename(columns=FIELD_MAP)

    df["parking_id"] = df["parking_id"].astype(str).str.strip()
    for col in ("capacity", "now_parked"):
        df[col] = pd.to_numeric(df[col], errors="coerce").round().astype("Int64")

    # 남은 자리 = 총 주차면 - 현재 주차 대수 (음수는 만차로 간주해 0으로)
    df["available"] = (df["capacity"] - df["now_parked"]).clip(lower=0)

    return df.reset_index(drop=True)


def empty_frame() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["parking_id", "parking_name", "address", "capacity",
                 "now_parked", "available", "updated_at"]
    )


def attach(df: pd.DataFrame, realtime: pd.DataFrame) -> pd.DataFrame:
    """주차장 테이블에 실시간 여유(now_parked/available/updated_at)를 붙인다.

    parking_id로 조인한다. 실시간 정보가 없는 주차장은 결측으로 남고,
    추천 로직의 availability_score()가 이를 0.5(중립)로 처리한다.

    총 주차면(capacity)도 실시간 API 값으로 덮어쓴다. 안내 정보 CSV의 총 주차면이
    오래돼서 실제와 다른 경우가 있는데(예: 총 1면인데 여유 7면), 그대로 두면
    여유 점수가 1을 넘어가는 이상한 값이 된다.
    """
    out = df.copy()
    for col in ("now_parked", "available", "updated_at"):
        if col in out.columns:
            out = out.drop(columns=col)

    if realtime.empty:
        out["now_parked"] = pd.Series(pd.NA, index=out.index, dtype="Int64")
        out["available"] = pd.Series(pd.NA, index=out.index, dtype="Int64")
        out["updated_at"] = pd.NA
        return out

    live = realtime[["parking_id", "capacity", "now_parked", "available", "updated_at"]].copy()
    live = live.rename(columns={"capacity": "_live_capacity"})
    live["parking_id"] = live["parking_id"].astype(str).str.strip()

    out["parking_id"] = out["parking_id"].astype(str).str.strip()
    out = out.merge(live, on="parking_id", how="left")

    if "capacity" in out.columns:
        base = pd.to_numeric(out["capacity"], errors="coerce").astype("Int64")
        out["capacity"] = out["_live_capacity"].fillna(base)
    else:
        out["capacity"] = out["_live_capacity"]
    return out.drop(columns="_live_capacity")


def main() -> None:
    if not config.SEOUL_OPENAPI_KEY:
        print("⚠ .env 에 SEOUL_OPENAPI_KEY 가 없습니다. (실시간 여유 정보는 생략됩니다)")
        print("  발급: https://data.seoul.go.kr/together/mypage/actkeyMain.do")
        return

    df = fetch()
    print(f"실시간 정보 제공 주차장: {len(df):,}곳")
    if not df.empty:
        print(f"총 주차면 합계: {df['capacity'].sum():,} / 현재 주차: {df['now_parked'].sum():,}")

    DEFAULT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(DEFAULT_OUTPUT, index=False, encoding="utf-8-sig")
    print(f"저장 완료 -> {DEFAULT_OUTPUT}")


if __name__ == "__main__":
    main()
