import pandas as pd
import os
from glob import glob

# 📂 경로 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

RAW_DIR = os.path.join(BASE_DIR, "..", "data", "raw", "enforcement_data")
CLEANED_DIR = os.path.join(BASE_DIR, "..", "data", "cleaned")

os.makedirs(CLEANED_DIR, exist_ok=True)

# ✅ 인코딩 자동 감지 함수
def read_csv_safe(file_path):
    encodings = ["cp949", "utf-8", "euc-kr"]

    for enc in encodings:
        try:
            return pd.read_csv(file_path, encoding=enc, low_memory=False)
        except:
            continue

    print(f"❌ 인코딩 실패: {file_path}")
    return None


# 📥 모든 CSV 가져오기
csv_files = glob(os.path.join(RAW_DIR, "*.csv"))

print(f"총 파일 개수: {len(csv_files)}")

all_data = []

for file in csv_files:
    print(f"\n📂 처리 중: {os.path.basename(file)}")

    df = read_csv_safe(file)

    if df is None:
        continue

    # 컬럼 확인
    if '구주소' not in df.columns:
        print("⚠️ '구주소' 컬럼 없음 → 스킵")
        continue

    # 종로구 필터링
    filtered = df[df['구주소'].astype(str).str.contains("종로구", na=False)]

    print(f"👉 필터링 결과: {len(filtered)}건")

    all_data.append(filtered)


# 🔥 하나로 합치기 (중복 제거 안 함)
if all_data:
    final_df = pd.concat(all_data, ignore_index=True)

    save_path = os.path.join(CLEANED_DIR, "종로구_단속정보_통합_데이터.csv")

    final_df.to_csv(save_path, index=False, encoding="utf-8-sig")

    print(f"\n🎉 최종 저장 완료!")
    print(f"📁 경로: {save_path}")
    print(f"📊 총 행 개수: {len(final_df)}")
else:
    print("❌ 저장할 데이터 없음")