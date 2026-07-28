CREATE DATABASE IF NOT EXISTS parking_project DEFAULT CHARACTER SET utf8mb4;
USE parking_project;

-- 1. 불법주정차 단속이력
CREATE TABLE IF NOT EXISTS ENFORCEMENT_HISTORY (
    history_id  INT AUTO_INCREMENT PRIMARY KEY,
    address     VARCHAR(255) NOT NULL,
    enforced_at DATETIME,
    latitude    DECIMAL(10, 8),
    longitude   DECIMAL(11, 8)
);

CREATE INDEX idx_enforcement_address ON ENFORCEMENT_HISTORY(address);
CREATE INDEX idx_enforcement_time ON ENFORCEMENT_HISTORY(enforced_at);

-- 2. 단속 CCTV 위치 정보
CREATE TABLE IF NOT EXISTS CCTV_INFO (
    cctv_id      INT AUTO_INCREMENT PRIMARY KEY,
    address      VARCHAR(255) NOT NULL,
    latitude     DECIMAL(10, 8),
    longitude    DECIMAL(11, 8),
    organization VARCHAR(100),
    purpose      VARCHAR(255)
);

-- 3. 주차장 정보
CREATE TABLE IF NOT EXISTS PARKING_LOT (
    parking_id     VARCHAR(50) PRIMARY KEY,
    parking_name   VARCHAR(255) NOT NULL,
    lot_category   VARCHAR(20),
    lot_type       VARCHAR(20),
    operation_rule VARCHAR(100),
    district       VARCHAR(50),
    address        VARCHAR(255) NOT NULL,
    latitude       DECIMAL(10, 8),
    longitude      DECIMAL(11, 8),
    phone          VARCHAR(50),
    capacity       INT,
    pay_type       VARCHAR(20),
    base_fee       INT,
    base_time      INT,
    add_fee        INT,
    add_time       INT,
    day_max_fee    INT,
    monthly_fee    INT,
    weekday_start  SMALLINT,
    weekday_end    SMALLINT,
    weekend_start  SMALLINT,
    weekend_end    SMALLINT,
    holiday_start  SMALLINT,
    holiday_end    SMALLINT,
    source         VARCHAR(50),
    fee            VARCHAR(255),
    operation_time VARCHAR(255)
);

CREATE INDEX idx_parking_district ON PARKING_LOT(district, lot_category);

-- 5-1. FAQ (연주)
CREATE TABLE IF NOT EXISTS FAQ (
    faq_id   INT AUTO_INCREMENT PRIMARY KEY,
    category VARCHAR(100),
    question VARCHAR(500) NOT NULL,
    answer   TEXT NOT NULL,
    source   VARCHAR(255)
);

-- 5-2. 민원 게시판 (연주/은미 - 종로구 공개 상담민원)
-- 예전 이름은 FAQ2 였는데 jem 브랜치에서 complain 으로 바꿨다.
-- pages/5_민원_게시판.py 와 loaders 가 모두 이 이름을 쓴다.
CREATE TABLE IF NOT EXISTS complain (
    faq2_id  INT AUTO_INCREMENT PRIMARY KEY,
    q_title  VARCHAR(100) NOT NULL,
    q_writer VARCHAR(10) NOT NULL,
    q_date   DATETIME NOT NULL,
    question TEXT NOT NULL,
    a_depart VARCHAR(50) NOT NULL,
    a_date   DATETIME NOT NULL,
    answer   TEXT NOT NULL
);

-- 6. 회원 정보
CREATE TABLE IF NOT EXISTS USERS (
    user_id       INT AUTO_INCREMENT PRIMARY KEY,
    username      VARCHAR(50)  NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 7. 사용자 주차기록
CREATE TABLE IF NOT EXISTS PARKING_LOG (
    log_id       INT AUTO_INCREMENT PRIMARY KEY,
    user_id      INT NOT NULL,
    parking_id   VARCHAR(50),
    parking_name VARCHAR(255),
    address      VARCHAR(255) NOT NULL,
    latitude     DECIMAL(10, 8),
    longitude    DECIMAL(11, 8),
    parked_at    DATETIME NOT NULL,
    is_charged   BOOLEAN NOT NULL DEFAULT FALSE,
    memo         VARCHAR(255),
    FOREIGN KEY (user_id) REFERENCES USERS(user_id) ON DELETE CASCADE
);

CREATE INDEX idx_parking_log_user_time ON PARKING_LOG(user_id, parked_at);


SELECT * FROM ENFORCEMENT_HISTORY;
SELECT * FROM CCTV_INFO;
SELECT * FROM PARKING_LOT;
SELECT * FROM FAQ;
SELECT * FROM complain;
SELECT * FROM USERS;
SELECT * FROM PARKING_LOG;

