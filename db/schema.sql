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

-- 3. 공영주차장 정보 (승희 - 서울시 공영주차장 안내 정보 CSV)
CREATE TABLE IF NOT EXISTS PUBLIC_PARKING_LOT (
    parking_id     INT PRIMARY KEY,          -- 공공데이터의 주차장코드 그대로 사용
    parking_name   VARCHAR(255) NOT NULL,
    address        VARCHAR(255) NOT NULL,
    latitude       DECIMAL(10, 8),
    longitude      DECIMAL(11, 8),
    fee            VARCHAR(255),
    operation_time VARCHAR(255)
);

-- 4. 민영주차장 정보 (승희 - 크롤링)
CREATE TABLE IF NOT EXISTS PRIVATE_PARKING_LOT (
    parking_id     INT AUTO_INCREMENT PRIMARY KEY,
    parking_name   VARCHAR(255) NOT NULL,
    address        VARCHAR(255),
    latitude       DECIMAL(10, 8),
    longitude      DECIMAL(11, 8),
    fee            VARCHAR(255),
    operation_time VARCHAR(255),
    source         VARCHAR(255)              -- 크롤링 출처 URL
);

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

-- 7. 사용자 주차기록 ("내 차 기억하기" 기능용)
CREATE TABLE IF NOT EXISTS PARKING_LOG (
    log_id     INT AUTO_INCREMENT PRIMARY KEY,
    user_id    INT NOT NULL,
    address    VARCHAR(255) NOT NULL,
    latitude   DECIMAL(10, 8),
    longitude  DECIMAL(11, 8),
    parked_at  DATETIME NOT NULL,
    is_charged BOOLEAN NOT NULL DEFAULT FALSE,
    FOREIGN KEY (user_id) REFERENCES USERS(user_id) ON DELETE CASCADE
);

CREATE INDEX idx_parking_log_user_time ON PARKING_LOG(user_id, parked_at);

SELECT count(*) FROM cctv_info;
SELECT*FROM cctv_info LIMIT 10;