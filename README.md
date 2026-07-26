# 주정차 제한 정보 조회 및 주변 주차장 안내 시스템

공공데이터 + 웹 크롤링 + Streamlit + 카카오맵 + MySQL(DBeaver) 기반 팀 프로젝트.
지금은 팀원별로 각자 페이지에서 작업하고, 완성 후 통합할 예정입니다
(FAQ 두 페이지는 최종적으로 한 페이지로 합칠 계획).

## 담당 매핑

| 담당 | 데이터 | 파일 |
|---|---|---|
| 치훈 | 서울시 불법주정차 단속 정보 (OA-22190) | `collectors/enforcement_history.py`, `pages/1_단속_다발구역.py` |
| 종원 | 단속 CCTV 위치정보 (OA-20471) | `collectors/cctv_api.py`, `pages/2_CCTV_지도.py` |
| 승희 | 주차정보안내시스템 크롤링(공영·민영, 좌표 100%) + 공영주차장 안내 정보 + 실시간 주차 여유 | `collectors/seoul_parking_crawler.py`, `collectors/public_parking_api.py`, `collectors/standard_parking_api.py`, `collectors/private_parking_crawler.py`, `collectors/realtime_parking_api.py`, `collectors/merge_parking.py`, `common/recommend.py`, `common/parking_data.py`, `pages/3_주차장_검색.py` |
| 연주 또는 은미 | 크롤링 A (FAQ - 이용안내 계열) | `collectors/faq_crawler_a.py`, `pages/4_FAQ_이용안내.py` |
| 연주 또는 은미 | 크롤링 B (FAQ - 단속·견인·이의신청 계열) | `collectors/faq_crawler_b.py`, `pages/5_FAQ_단속견인.py` |

## 폴더 구조

```
.
├── main.py                    # Streamlit 진입점 (uv run streamlit run main.py)
├── config.py                  # .env 로더 (MySQL 접속정보, 카카오/공공데이터 키)
├── pyproject.toml / uv.lock   # uv 의존성
├── .env.example               # 환경변수 템플릿 (실제 .env는 git 제외)
│
├── pages/                     # Streamlit 멀티페이지 (사이드바에 자동 표시)
│   ├── 1_단속_다발구역.py      # 치훈
│   ├── 2_CCTV_지도.py          # 종원
│   ├── 3_주차장_검색.py        # 승희
│   ├── 4_FAQ_이용안내.py       # 연주 또는 은미  ┐ 추후 한 페이지로
│   └── 5_FAQ_단속견인.py       # 연주 또는 은미  ┘ 통합 예정
│
├── common/                    # 공유 유틸
│   ├── db.py                  # MySQL 연결 + read_sql/execute
│   ├── kakao_map.py           # 카카오맵 HTML 빌더 (커스텀 마커/말풍선/범례/지오코딩)
│   ├── geo.py                 # 거리 계산 (지오코딩 함수 포함 - REST 키 발급 시 사용)
│   ├── recommend.py           # 승희 - 예상요금·운영여부·추천 점수 (순수 함수, 자체 테스트 포함)
│   ├── parking_data.py        # 승희 - 주차장 검색 페이지 데이터 로더 (DB -> CSV -> 원본 순 폴백)
│   └── ui.py                  # 공통 디자인 (CSS, 히어로 배너, 카드, 상태 칩)
│
├── collectors/                # 데이터 수집 스크립트 (담당자별)
│   ├── enforcement_history.py     # 치훈 - 단속이력 CSV 정제 + 다발구역 집계
│   ├── cctv_api.py                # 종원 - 서울 열린데이터광장 Open API
│   ├── seoul_parking_crawler.py   # 승희 - 주차정보안내시스템 크롤링 (공영·민영, 좌표 100%) ★주력
│   ├── public_parking_api.py      # 승희 - 공영주차장 (서울시 OA-13122 CSV)
│   ├── standard_parking_api.py    # 승희 - 전국주차장정보표준데이터 (민영·부설, CSV/API)
│   ├── private_parking_crawler.py # 승희 - 민영·부설만 추려 적재용 CSV 생성
│   ├── realtime_parking_api.py    # 승희 - 실시간 주차 여유 (서울시 OA-21709)
│   ├── merge_parking.py           # 승희 - 소스 통합 + 중복 제거 (이름 정규화 + 좌표 50m)
│   ├── faq_crawler_a.py           # 연주 또는 은미 - 서울시설공단 FAQ (정적, 확인됨)
│   └── faq_crawler_b.py           # 연주 또는 은미 - 견인/민원링크/고시공고
│
├── db/
│   └── schema.sql             # 전체 테이블 CREATE문 (DBeaver에서 실행)
│
├── loaders/
│   └── load_to_db.py          # 정제 CSV → MySQL 적재 공통 스크립트
│
└── data/
    ├── raw/                   # 수집 원본
    └── cleaned/               # 정제 결과 (loaders가 여기서 읽음)
```
## ERD
```mermaid
erDiagram
    %% ============================================================
    %% 주정차 제한 정보 조회 및 주변 주차장 안내 시스템 - ERD
    %% GitHub README나 발표자료에 그대로 붙여넣으면 렌더링됩니다.
    %% ============================================================

    USERS ||--o{ PARKING_LOG : "주차기록 보유"

    ENFORCEMENT_HISTORY {
        INT history_id PK "AUTO_INCREMENT"
        VARCHAR address "단속 주소 (idx)"
        DATETIME enforced_at "단속일시 (idx)"
        DECIMAL latitude
        DECIMAL longitude
    }

    CCTV_INFO {
        INT cctv_id PK "AUTO_INCREMENT"
        VARCHAR address "설치 주소"
        DECIMAL latitude
        DECIMAL longitude
        VARCHAR organization "관리기관"
        VARCHAR purpose "설치 목적"
    }

    PUBLIC_PARKING_LOT {
        VARCHAR parking_id PK "공공데이터 주차장코드"
        VARCHAR parking_name
        VARCHAR lot_category "공영 / 민영"
        VARCHAR lot_type "노상 / 노외 / 부설"
        VARCHAR district "자치구 (idx)"
        VARCHAR address
        DECIMAL latitude
        DECIMAL longitude
        INT capacity "총 주차면"
        INT base_fee "기본요금(원)"
        INT base_time "기본시간(분)"
        INT add_fee "추가 단위요금(원)"
        INT add_time "추가 단위시간(분)"
        INT day_max_fee "일 최대요금(원)"
        SMALLINT weekday_start "평일 시작 HHMM"
        SMALLINT weekday_end "평일 종료 HHMM"
        SMALLINT weekend_start "주말 시작 HHMM"
        SMALLINT weekend_end "주말 종료 HHMM"
        VARCHAR source "seoul_public / standard"
        VARCHAR fee "표시용 요금 문구"
        VARCHAR operation_time "표시용 운영시간 문구"
    }

    PRIVATE_PARKING_LOT {
        VARCHAR parking_id PK "표준데이터 주차장관리번호"
        VARCHAR parking_name
        VARCHAR lot_category "민영 / 부설"
        VARCHAR lot_type "노상 / 노외 / 부설"
        VARCHAR district "자치구 (idx)"
        VARCHAR address
        DECIMAL latitude
        DECIMAL longitude
        INT capacity
        INT base_fee
        INT base_time
        INT add_fee
        INT add_time
        INT day_max_fee
        SMALLINT weekday_start
        SMALLINT weekday_end
        SMALLINT weekend_start
        SMALLINT weekend_end
        VARCHAR source "standard / crawl"
        VARCHAR fee
        VARCHAR operation_time
    }

    FAQ {
        INT faq_id PK "AUTO_INCREMENT"
        VARCHAR category "크롤링 A/B 구분 기준"
        VARCHAR question
        TEXT answer
        VARCHAR source "출처 URL"
    }

    USERS {
        INT user_id PK "AUTO_INCREMENT"
        VARCHAR username UK "중복 불가"
        VARCHAR password_hash "해시 저장 (평문 금지)"
        DATETIME created_at
    }

    PARKING_LOG {
        INT log_id PK "AUTO_INCREMENT"
        INT user_id FK "USERS.user_id (CASCADE)"
        VARCHAR address
        DECIMAL latitude
        DECIMAL longitude
        DATETIME parked_at
        BOOLEAN is_charged "유료 여부"
    }
```

## 처음 시작할 때 (팀원 각자 1회)

```bash
git clone <repo-url>
cd <repo>
uv sync                        # pyproject.toml/uv.lock 기준으로 가상환경 자동 생성
cp .env.example .env           # .env 열어서 값 채우기
```

`.env`에 채울 값 (현재 사용하는 키는 2개 + MySQL 접속정보):

- `MYSQL_*` — DBeaver에서 만든 로컬 MySQL 접속 정보
- `KAKAO_JS_KEY` — 카카오 개발자 콘솔 > 앱 키 > **JavaScript 키** (지도 표시용)
- `DATA_GO_KR_API_KEY` — 공공데이터포털(data.go.kr) 인증키

`SEOUL_OPENAPI_KEY`(서울 열린데이터광장)는 종원 담당 CCTV Open API를 쓸 때
필요해지면 그때 `.env`에 추가하면 됩니다 (없어도 앱은 동작).

## DB 만들기 (1회, DBeaver에서)

```sql
CREATE DATABASE parking_project DEFAULT CHARACTER SET utf8mb4;
```

이후 `parking_project`를 선택한 상태에서 `db/schema.sql` 전체를 실행합니다.

## 실행

```bash
uv run streamlit run main.py
```

DB나 카카오 키가 아직 없어도 모든 페이지는 샘플 데이터로 동작합니다.

## 데이터 수집 -> 정제 -> 적재 흐름

1. `collectors/`의 본인 담당 스크립트 실행 → `data/raw/` 또는 `data/cleaned/`에 저장
2. `uv run python loaders/load_to_db.py --csv data/cleaned/xxx.csv --table 테이블명` 으로 MySQL 적재
3. Streamlit 페이지에서 확인 (`@st.cache_data` 캐시 때문에 바로 안 보이면 10분 대기 또는 앱 재시작)

### 주차장 검색 (승희) 파이프라인

현재 검색 범위는 **종로구**입니다 (`common/parking_data.py`의 `SITE_DISTRICTS`).
다른 구를 추가하려면 크롤러를 그 구로 한 번 돌려 `data/cleaned/site_parking.csv`를 다시 만들면 됩니다.

```bash
uv run python collectors/seoul_parking_crawler.py --district 종로구   # 232곳, 좌표 100%
uv run python collectors/seoul_parking_crawler.py --district all      # 서울 25개구
```

DB나 정제 CSV가 없어도 저장소의 CSV로 페이지가 바로 동작합니다.
아래는 정식으로 DB에 넣고 싶을 때의 순서입니다.

```bash
uv run python collectors/public_parking_api.py                       # 공영 850곳 (보조)
uv run python collectors/realtime_parking_api.py                     # 실시간 여유 122곳
uv run python collectors/private_parking_crawler.py                  # 표준데이터 민영 (선택)
uv run python loaders/load_to_db.py --csv data/cleaned/public_parking.csv  --table PUBLIC_PARKING_LOT  --if-exists truncate
uv run python loaders/load_to_db.py --csv data/cleaned/private_parking.csv --table PRIVATE_PARKING_LOT --if-exists truncate
```

로직 검증은 스트림릿 없이 단독 실행됩니다.

```bash
uv run python common/recommend.py          # 예상요금·운영여부·추천 점수 테스트
uv run python collectors/merge_parking.py  # 이름 정규화·중복 제거 테스트
```

## 데이터 소스 메모 (실제로 열어서 확인한 결과)

| 소스 | 형태 | 비고 |
|---|---|---|
| 서울시 불법주정차 단속 정보 (OA-22190) | CSV 다운로드 (분기별 12개) | 단속일시/단속주소/위도/경도 |
| 서울시 단속 CCTV 위치정보 (OA-20471) | Open API (서울 열린데이터광장 키 필요) | 파일 다운로드 미제공 |
| **서울특별시 주차정보안내시스템** (parking.seoul.go.kr) | 내부 AJAX(`SearchParkingBy.do`) 크롤링 | **주력 소스.** 자치구 단위로 공영·민영·부설을 모두 주고 **좌표 100%**. 종로구 232곳 (공영 52 / 민영 180). 페이징 없음 |
| 서울시 공영주차장 안내 정보 (OA-13122) | CSV 다운로드 (`seoul_parking.csv`, EUC-KR) | 서울 전체 2,189행 → 좌표 병합 후 850곳. **좌표가 117곳뿐**이라 단독으로는 지도가 비어서, 위 크롤링 데이터의 보조(일 최대요금·정기권 보완)로 사용 |
| 서울시 실시간 주차정보 (OA-21709) | Open API (`SEOUL_OPENAPI_KEY`) | 시영주차장 122곳의 현재 주차대수 → 추천의 '여유 점수'에 사용 |
| 전국주차장정보표준데이터 | CSV 다운로드 또는 API (`DATA_GO_KR_API_KEY`) | **민영·부설의 유일한 소스.** `data/raw/national_parking.csv`로 저장하면 자동 인식 |
| 서울시설공단 공영주차장 FAQ (sisul.or.kr) | 정적 게시판 | requests+bs4로 크롤링 확인됨 |
| 종로구시설관리공단 견인 안내 (ijongno.co.kr/www/422) | 정적 페이지 | requests+bs4로 크롤링 확인됨 |
| 서울시 고시공고 '주정차' 키워드 | JS 렌더링 | Selenium 필요 (faq_crawler_b.py TODO) |
| 새올민원창구/응답소/국민신문고 | 로그인 필요 | 크롤링 대신 안내 링크로 수록 |

