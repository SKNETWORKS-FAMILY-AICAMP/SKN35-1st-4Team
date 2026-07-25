"""
프로젝트 공통 환경설정 로더.

.env 파일에서 MySQL 접속 정보, 카카오 키 등을 읽어온다.
Streamlit 페이지든, collectors/loaders의 일반 스크립트든
전부 이 파일 하나만 import해서 쓰면 된다.

사용 전 준비
    cp .env.example .env
    # .env 파일을 열어 실제 값 입력 (이 파일은 git에 올리지 않음)

현재 팀에서 사용하는 키는 2개:
    KAKAO_JS_KEY        - 카카오맵 지도 표시용 (JavaScript 키)
    DATA_GO_KR_API_KEY  - 공공데이터포털(data.go.kr) API용

DB는 로컬 MySQL (DBeaver로 관리). 나중에 TiDB Cloud로 옮기게 되면
.env 값만 바꾸면 되도록 변수명을 범용(MYSQL_*)으로 잡아뒀다.
"""

import os

from dotenv import load_dotenv

load_dotenv()  # .env 파일을 환경변수로 로드

# ── 로컬 MySQL (DBeaver로 관리) ────────────────────────────────
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "")

# ── 지금 사용하는 API 키 2개 ───────────────────────────────────
KAKAO_JS_KEY = os.getenv("KAKAO_JS_KEY", "")
DATA_GO_KR_API_KEY = os.getenv("DATA_GO_KR_API_KEY", "")

# ── 나중에 필요해지면 .env에 추가해서 쓰는 키 (없어도 앱은 동작) ──
# 서울 열린데이터광장(data.seoul.go.kr) - 종원 담당 CCTV Open API를 쓸 경우 필요
SEOUL_OPENAPI_KEY = os.getenv("SEOUL_OPENAPI_KEY", "")


def is_db_configured() -> bool:
    """.env에 MySQL 접속 정보가 채워져 있는지 확인.

    로컬 MySQL은 비밀번호가 비어있는 경우도 있어서 password는 필수로 보지 않는다.
    """
    return all([MYSQL_HOST, MYSQL_USER, MYSQL_DATABASE])