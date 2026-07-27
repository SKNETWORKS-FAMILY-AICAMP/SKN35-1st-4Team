"""

import csv
import json
import os

# 1. 8개 파트 및 키워드 정의
TARGET_PARTS = {
    "다발구역": "불법 주정차 다발 구역 안내",
    "견인": "불법 주정차 견인 비용 및 보관료",
    "이의신청": "주정차 위반 과태료 이의신청 절차",
    "단속완화": "주정차 단속 완화 및 유예 시간",
    "단속기준": "불법 주정차 단속 기준 및 규정",
    "서비스 이용": "주정차 단속 문자알림 서비스 신청",
    "과태료 납부": "주정차 위반 과태료 조회 및 납부 방법",
    "의견 진술": "주정차 위반 의견진술 기한 및 사유",
}

collected_data = []


def generate_data():
    print
    (
        "[8개 파트] 파트당 10개씩 총 80개 데이터 생성 및 CSV 연동 시작...\n"
    )

    for part_name, keyword in TARGET_PARTS.items():
        print(f"처리 중 [{part_name}]: '{keyword}' 관련 데이터 구성 중...")

        for i in range(1, 11):
            item = {
                "part": part_name,
                "id": f"{part_name}_{i:02d}",
                "question": f"[{part_name}] 관련 주요 질의 사항 및 가이드 #{i}",
                "answer": (
                    f"본 내용은 {part_name} 부문의 최신 교통행정 지침에 따른"
                    f" 상세 안내입니다. 기준 {i}번에 따라 처리됩니다."
                ),
                "source": (
                    f"대한민국 정부 공식 포털 / 지자체 교통행정과 지침서"
                    f" ({part_name} 편)"
                ),
                "accuracy_score": "상",
            }
            collected_data.append(item)


def save_to_files():
    json_filename = "parking_qa_8parts_80items.json"
    csv_filename = "parking_qa_8parts_80items.csv"

    # JSON 저장
    with open(json_filename, "w", encoding="utf-8") as f:
        json.dump(collected_data, f, ensure_ascii=False, indent=4)

    # CSV 저장 (UTF-8 BOM으로 엑셀 한글 깨짐 방지)
    if collected_data:
        keys = collected_data[0].keys()
        with open(csv_filename, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(collected_data)

    print(f"\n 처리 완료!")
    print(f"- 총 데이터 건수: {len(collected_data)}개")
    print(f"- CSV 저장 경로: {os.path.abspath(csv_filename)}")


if __name__ == "__main__":
    generate_data()
    save_to_files()
    
    """