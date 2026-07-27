"""
[담당: 승희] 회원가입 · 로그인 (USERS 테이블).

저장소
    .env 에 MySQL 접속 정보가 있으면 MySQL, 없으면 data/app.db (SQLite)를 쓴다.
    나중에 .env 만 채우면 코드 수정 없이 MySQL로 넘어간다.
    테이블 정의는 db/schema.sql 과 같고, 없으면 처음 한 번 자동 생성한다.

비밀번호는 절대 평문으로 저장하지 않는다.
    pbkdf2_sha256$반복횟수$salt$해시   형태의 문자열 하나로 USERS.password_hash 에 넣는다.
    표준 라이브러리(hashlib)만 쓰므로 추가 패키지가 필요 없다.
    사용자마다 다른 salt를 붙여서, 같은 비밀번호라도 해시가 달라진다.

로그인 상태는 st.session_state["user"] 에 {"user_id", "username"} 로 들어간다.
브라우저 탭을 닫으면 사라지는 세션이라 별도 로그아웃 없이도 안전하다.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import sys
from pathlib import Path

import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402

LOCAL_DB = ROOT / "data/app.db"

# pbkdf2 반복 횟수. 높을수록 무차별 대입이 느려지지만 로그인도 느려진다.
ITERATIONS = 200_000
SALT_BYTES = 16

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")
MIN_PASSWORD = 8

SESSION_KEY = "user"


# ---------------------------------------------------------------------------
# 저장소
# ---------------------------------------------------------------------------
@st.cache_resource
def get_engine() -> Engine:
    """MySQL이 설정돼 있으면 MySQL, 아니면 로컬 SQLite 엔진."""
    if config.is_db_configured():
        from common.db import get_engine as mysql_engine

        return mysql_engine()

    LOCAL_DB.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{LOCAL_DB}")


def is_mysql() -> bool:
    return get_engine().dialect.name != "sqlite"


def storage_label() -> str:
    """화면에 표시할 저장소 설명."""
    return f"MySQL {config.MYSQL_DATABASE}" if is_mysql() else f"SQLite {LOCAL_DB.name}"


# MySQL과 SQLite는 자동증가 PK 문법이 달라서 DDL만 따로 둔다.
_DDL = {
    "mysql": [
        """CREATE TABLE IF NOT EXISTS USERS (
            user_id       INT AUTO_INCREMENT PRIMARY KEY,
            username      VARCHAR(50)  NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS PARKING_LOG (
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
        )""",
    ],
    "sqlite": [
        """CREATE TABLE IF NOT EXISTS USERS (
            user_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at    TEXT DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS PARKING_LOG (
            log_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL,
            parking_id   TEXT,
            parking_name TEXT,
            address      TEXT NOT NULL,
            latitude     REAL,
            longitude    REAL,
            parked_at    TEXT NOT NULL,
            is_charged   INTEGER NOT NULL DEFAULT 0,
            memo         TEXT,
            FOREIGN KEY (user_id) REFERENCES USERS(user_id) ON DELETE CASCADE
        )""",
    ],
}


@st.cache_resource
def ensure_tables() -> None:
    """USERS / PARKING_LOG 테이블이 없으면 만든다 (프로세스당 1회)."""
    dialect = "mysql" if is_mysql() else "sqlite"
    with get_engine().begin() as conn:
        for ddl in _DDL[dialect]:
            conn.execute(text(ddl))


# ---------------------------------------------------------------------------
# 비밀번호 해싱
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    """평문 비밀번호 -> 'pbkdf2_sha256$반복$salt$해시' 문자열."""
    salt = os.urandom(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """입력 비밀번호가 저장된 해시와 맞는지 확인."""
    try:
        algorithm, iterations, salt_hex, digest_hex = stored.split("$")
    except (AttributeError, ValueError):
        return False
    if algorithm != "pbkdf2_sha256":
        return False

    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations)
    )
    # 타이밍 공격을 막기 위해 == 대신 compare_digest 사용
    return hmac.compare_digest(digest.hex(), digest_hex)


# ---------------------------------------------------------------------------
# 회원가입 / 로그인
# ---------------------------------------------------------------------------
def signup(username: str, password: str, password2: str) -> tuple[bool, str]:
    """회원가입. (성공여부, 메시지)를 돌려준다."""
    username = (username or "").strip()

    if not USERNAME_RE.match(username):
        return False, "아이디는 영문·숫자·밑줄 3~20자여야 합니다."
    if len(password or "") < MIN_PASSWORD:
        return False, f"비밀번호는 {MIN_PASSWORD}자 이상이어야 합니다."
    if password != password2:
        return False, "비밀번호가 서로 다릅니다."

    ensure_tables()
    with get_engine().begin() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM USERS WHERE username = :u"), {"u": username}
        ).first()
        if exists:
            return False, "이미 사용 중인 아이디입니다."

        conn.execute(
            text("INSERT INTO USERS (username, password_hash) VALUES (:u, :p)"),
            {"u": username, "p": hash_password(password)},
        )
    return True, f"{username} 님, 가입이 완료됐습니다. 로그인해주세요."


def login(username: str, password: str) -> tuple[bool, str]:
    """로그인 성공 시 세션에 사용자 정보를 넣는다."""
    username = (username or "").strip()
    ensure_tables()

    with get_engine().connect() as conn:
        row = conn.execute(
            text("SELECT user_id, username, password_hash FROM USERS WHERE username = :u"),
            {"u": username},
        ).first()

    # 아이디가 없을 때와 비밀번호가 틀렸을 때 메시지를 같게 둔다
    # (다르게 하면 어떤 아이디가 존재하는지 알려주는 셈이 된다)
    if row is None or not verify_password(password, row.password_hash):
        return False, "아이디 또는 비밀번호가 올바르지 않습니다."

    st.session_state[SESSION_KEY] = {"user_id": int(row.user_id), "username": row.username}
    return True, f"{row.username} 님, 환영합니다."


def logout() -> None:
    st.session_state.pop(SESSION_KEY, None)


def current_user() -> dict | None:
    """로그인한 사용자 {"user_id", "username"} 또는 None."""
    return st.session_state.get(SESSION_KEY)


def require_login(message: str = "이 기능은 로그인 후 이용할 수 있습니다.") -> dict:
    """로그인 안 했으면 안내를 띄우고 페이지 실행을 멈춘다."""
    user = current_user()
    if user is None:
        st.info(message, icon="🔒")
        st.page_link("pages/6_로그인_회원가입.py", label="로그인 · 회원가입 하러 가기")
        st.stop()
    return user
