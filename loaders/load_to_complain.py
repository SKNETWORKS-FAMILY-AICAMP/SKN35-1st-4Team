from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

# 프로젝트 루트 경로 추가 (common 모듈을 가져오기 위함)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT) )

from common.db import execute, get_engine


def main() -> None:
    # 1. 대상 CSV 파일 및 DB 테이블 지정
    csv_path = ROOT / 'data' / 'cleaned' / 'complain_faq2_result.csv'
    table_name = 'complain'

    # 2.csv 존재 여부 체크
    if not csv_path.exists():
        print(f'csv 파일을 찾을 수 없습니다. {csv_path}')
        return

    # 3.csv 읽기
    df = pd.read_csv(csv_path, encoding='utf-8-sig')
    print(f'csv 읽기 완료 : {csv_path.name} ({len(df):,})')

    # 4. NOT NULL 제약조건 대비 결측치 채우기
    df['q_title'] = df['q_title'].fillna("제목 없음")
    df['q_writer'] = df['q_writer'].fillna('-')
    df['question'] = df['question'].fillna('질문 내용 없음')
    df['a_depart'] = df['a_depart'].fillna('-')
    df['answer'] = df['answer'].fillna('답변 내용 없음')

    # 5. 날짜 포맷 변환
    df['q_date'] = pd.to_datetime(df['q_date'], errors='coerce')
    df['a_date'] = pd.to_datetime(df['a_date'], errors = 'coerce')

    # 6. DB 적재
    try :
        engine = get_engine()

        # if_exists='append' : 기존 데이터를 삭제하지 않고 그대로 뒤에 이어 붙임.
        df.to_sql(table_name, engine, if_exists='append', index=False)
        print(f'적재 성공! 총 {len(df):,}건이 {table_name} 테이블에 추가되었습니다.')

    except Exception as e:
        print(f'DB 적재 중 오류 발생 {e}')


if __name__ == '__main__':
    main()