-- ============================================================
-- 주정차 제한 정보 조회 및 주변 주차장 안내 시스템 - 전체 스키마
-- 로컬 MySQL 기준 (DBeaver에서 실행)
--
-- 사용법: DBeaver에서 아래 순서로 실행
--   1) CREATE DATABASE parking_project DEFAULT CHARACTER SET utf8mb4;
--   2) USE parking_project;
--   3) 이 파일 전체 실행
-- ============================================================

-- 1. 불법주정차 단속이력 (치훈 - data.seoul.go.kr OA-22190 CSV)
--    -> address별 건수를 집계하면 "다발구역"(단속이 자주 발생하는 곳) 랭킹이 된다.
CREATE TABLE IF NOT EXISTS ENFORCEMENT_HISTORY (
    history_id  INT AUTO_INCREMENT PRIMARY KEY,
    address     VARCHAR(255) NOT NULL,
    enforced_at DATETIME,
    latitude    DECIMAL(10, 8),
    longitude   DECIMAL(11, 8)
);

CREATE INDEX idx_enforcement_address ON ENFORCEMENT_HISTORY(address);
CREATE INDEX idx_enforcement_time ON ENFORCEMENT_HISTORY(enforced_at);

-- 2. 단속 CCTV 위치 정보 (종원 - data.seoul.go.kr OA-20471)
CREATE TABLE IF NOT EXISTS CCTV_INFO (
    cctv_id      INT AUTO_INCREMENT PRIMARY KEY,
    address      VARCHAR(255) NOT NULL,
    latitude     DECIMAL(10, 8),
    longitude    DECIMAL(11, 8),
    organization VARCHAR(100),
    purpose      VARCHAR(255)
);

-- 3. 주차장 정보 (승희) - 공영·민영을 한 테이블에서 관리
--   공영/민영 구분은 테이블이 아니라 lot_category 컬럼으로 한다.
--   컬럼 구성이 완전히 같은 두 테이블을 두면 구분 정보가 테이블명과 컬럼에
--   중복 저장되고, 같은 주차장이 양쪽에 들어가도 PK가 막아주지 못한다.
--   요금/운영시간을 숫자로 갖고 있어야 예상요금·추천 점수를 계산할 수 있고,
--   운영시각은 원본 그대로 HHMM 정수(0=00:00, 2400=24:00)로 저장한다.
--   적재: uv run python loaders/load_to_db.py \
--             --csv data/cleaned/parking_lot.csv --table PARKING_LOT --if-exists truncate
CREATE TABLE IF NOT EXISTS PARKING_LOT (
    parking_id     VARCHAR(50) PRIMARY KEY,  -- 서울시 주차장코드 / STD-xxx(표준데이터)
    parking_name   VARCHAR(255) NOT NULL,
    lot_category   VARCHAR(20),              -- 공영 / 민영
    lot_type       VARCHAR(20),              -- 노상 / 노외 / 부설
    operation_rule VARCHAR(100),             -- 시간제 / 거주자우선 / 실시간 연계여부 등
    district       VARCHAR(50),              -- 자치구 (주소에서 추출)
    address        VARCHAR(255) NOT NULL,
    latitude       DECIMAL(10, 8),
    longitude      DECIMAL(11, 8),
    phone          VARCHAR(50),
    capacity       INT,                      -- 총 주차면
    pay_type       VARCHAR(20),              -- 유료 / 무료
    base_fee       INT,                      -- 기본 주차 요금(원)
    base_time      INT,                      -- 기본 주차 시간(분)
    add_fee        INT,                      -- 추가 단위 요금(원)
    add_time       INT,                      -- 추가 단위 시간(분)
    day_max_fee    INT,                      -- 일 최대 요금(원, 0이면 상한 없음)
    monthly_fee    INT,                      -- 월 정기권 금액(원)
    weekday_start  SMALLINT,                 -- 평일 운영 시작 HHMM
    weekday_end    SMALLINT,
    weekend_start  SMALLINT,
    weekend_end    SMALLINT,
    holiday_start  SMALLINT,
    holiday_end    SMALLINT,
    source         VARCHAR(50),              -- seoul_site / seoul_public / standard
    fee            VARCHAR(255),             -- 표시용 요금 문구
    operation_time VARCHAR(255)              -- 표시용 운영시간 문구
);

CREATE INDEX idx_parking_district ON PARKING_LOT(district, lot_category);

-- 4. (예약) 3번 테이블로 통합됨
--    이전 스키마의 PUBLIC_PARKING_LOT / PRIVATE_PARKING_LOT 를 이미 만들었다면:
--      DROP TABLE IF EXISTS PUBLIC_PARKING_LOT;
--      DROP TABLE IF EXISTS PRIVATE_PARKING_LOT;

-- 5. FAQ (은미: 이용안내 계열 / 연주: 단속·견인·이의신청 계열 - 같은 테이블 공유)
CREATE TABLE IF NOT EXISTS FAQ (
    faq_id   INT AUTO_INCREMENT PRIMARY KEY,
    category VARCHAR(100),
    question VARCHAR(500) NOT NULL,
    answer   TEXT NOT NULL,
    source   VARCHAR(255)
);

-- 6. 회원 정보 (로그인/개인화 기능용)
CREATE TABLE IF NOT EXISTS USERS (
    user_id       INT AUTO_INCREMENT PRIMARY KEY,
    username      VARCHAR(50)  NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 7. 사용자 주차기록 (승희 - "내 차 기억하기" 기능용)
--   주차장 목록에서 고르면 parking_id/parking_name이 채워지고,
--   노상처럼 등록된 주차장이 아니면 address만 채워진다.
--   parking_name을 따로 저장(비정규화)하는 이유: 주차장 목록이 DB가 아니라 CSV에서
--   올 수도 있어 PARKING_LOT 조인이 항상 되지는 않는다. 기록 시점 이름을 남기는 효과도 있다.
CREATE TABLE IF NOT EXISTS PARKING_LOG (
    log_id       INT AUTO_INCREMENT PRIMARY KEY,
    user_id      INT NOT NULL,
    parking_id   VARCHAR(50),              -- PARKING_LOT.parking_id (직접 입력이면 NULL)
    parking_name VARCHAR(255),             -- 표시용 주차장명 (직접 입력이면 NULL)
    address      VARCHAR(255) NOT NULL,
    latitude     DECIMAL(10, 8),
    longitude    DECIMAL(11, 8),
    parked_at    DATETIME NOT NULL,
    is_charged   BOOLEAN NOT NULL DEFAULT FALSE,
    memo         VARCHAR(255),
    FOREIGN KEY (user_id) REFERENCES USERS(user_id) ON DELETE CASCADE
);

-- 이전 스키마로 PARKING_LOG를 이미 만들었다면 컬럼만 추가하면 된다:
--   ALTER TABLE PARKING_LOG ADD COLUMN parking_id VARCHAR(50) AFTER user_id;
--   ALTER TABLE PARKING_LOG ADD COLUMN parking_name VARCHAR(255) AFTER parking_id;
--   ALTER TABLE PARKING_LOG ADD COLUMN memo VARCHAR(255);

CREATE INDEX idx_parking_log_user_time ON PARKING_LOG(user_id, parked_at);

SELECT count(*) FROM cctv_info;
SELECT*FROM cctv_info LIMIT 10;