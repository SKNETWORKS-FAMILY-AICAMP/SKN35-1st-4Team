"""
[담당: 승희] 주차장·CCTV·단속이력 3종을 DB에 한 번에 적재한다.

    uv run python loaders/load_all.py              # 3개 전부 다시 적재
    uv run python loaders/load_all.py --only CCTV_INFO PARKING_LOT
    uv run python loaders/load_all.py --if-exists append

접속 대상은 .env(또는 st.secrets)의 DB_* 값을 따른다. 로컬 MySQL이든
TiDB Cloud든 코드는 그대로고 접속 정보만 바꾸면 된다.

기본 모드가 truncate 인 이유: 이 3개는 원본 CSV가 정답인 "다시 만들 수 있는"
테이블이라 매번 통째로 갈아끼우는 게 맞다. append 로 두면 재실행할 때마다
같은 행이 쌓여 단속 건수가 부풀고, 위험도 판정이 그대로 틀어진다.
(USERS/PARKING_LOG 는 사용자가 만든 데이터라 여기서 절대 건드리지 않는다.)
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from loaders.load_to_db import load_csv  # noqa: E402

# (테이블, CSV 경로, 설명) — 순서대로 적재한다.
# 단속이력은 23만 건이라 제일 오래 걸려서 마지막에 둔다.
TARGETS: list[tuple[str, Path, str]] = [
    ("PARKING_LOT", ROOT / "data/cleaned/parking_lot.csv", "주차장"),
    ("CCTV_INFO", ROOT / "data/cleaned/cctv_cleaned.csv", "단속 CCTV"),
    ("FAQ", ROOT / "data/cleaned/FAQ_sample_.csv", "FAQ"),
    ("FAQ2", ROOT / "data/cleaned/complain_faq2_result.csv", "민원 게시판"),
    (
        "ENFORCEMENT_HISTORY",
        ROOT / "data/cleaned/종로구_단속정보_통합_데이터.csv",
        "단속 이력",
    ),
]


def main() -> None:
    parser = argparse.ArgumentParser(description="주차장·CCTV·단속이력 일괄 적재")
    parser.add_argument(
        "--only",
        nargs="+",
        metavar="TABLE",
        help="이 테이블만 적재 (기본: 전부)",
    )
    parser.add_argument(
        "--if-exists",
        default="truncate",
        choices=["append", "replace", "truncate"],
        help="기존 데이터 처리 방식 (기본: truncate — 비우고 새로 넣기)",
    )
    args = parser.parse_args()

    targets = TARGETS
    if args.only:
        wanted = {name.upper() for name in args.only}
        unknown = wanted - {table for table, _, _ in TARGETS}
        if unknown:
            print(f"✗ 모르는 테이블: {', '.join(sorted(unknown))}")
            print(f"  가능한 값: {', '.join(t for t, _, _ in TARGETS)}")
            raise SystemExit(2)
        targets = [item for item in TARGETS if item[0] in wanted]

    # CSV가 하나라도 없으면 절반만 적재된 DB를 만들지 말고 미리 멈춘다.
    # (단속이력 CSV는 용량 때문에 git에 없어서 새로 받은 clone에서 자주 빠진다.)
    missing = [str(path.relative_to(ROOT)) for _, path, _ in targets if not path.exists()]
    if missing:
        print("✗ CSV 파일이 없습니다:")
        for path in missing:
            print(f"    {path}")
        print("\n  주차장 CSV: uv run python collectors/seoul_parking.py")
        print("  단속이력 CSV: 용량이 커서 git에 없습니다. 팀원에게 받아주세요.")
        raise SystemExit(1)

    started = time.time()
    loaded: list[tuple[str, int]] = []

    for index, (table, path, label) in enumerate(targets, start=1):
        print(f"\n=== {index}/{len(targets)} {label} ({table}) ===")
        rows = load_csv(path, table, args.if_exists)
        loaded.append((table, rows))

    print(f"\n완료 ({time.time() - started:.1f}초)")
    for table, rows in loaded:
        print(f"  {table:22s} {rows:>9,}행")
    print("\n확인: uv run python loaders/check_db.py")


if __name__ == "__main__":
    main()
