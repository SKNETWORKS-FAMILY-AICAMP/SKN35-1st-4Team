"""
프로젝트 공통 환경설정 로더.

.env 파일에서 MySQL 접속 정보, 카카오 키 등을 읽어온다.
Streamlit 페이지든, collectors/loaders의 일반 스크립트든
전부 이 파일 하나만 import해서 쓰면 된다.

사용 전 준비
    cp .env.example .env
    # .env 파일을 열어 실제 값 입력 (이 파일은 git에 올리지 않음)

현재 팀에서 사용하는 키:
    KAKAO_JS_KEY        - 카카오맵 지도 표시용 (JavaScript 키)
    KAKAO_REST_KEY      - 주소 -> 좌표 변환(로컬 API)용 (REST API 키)
    DATA_GO_KR_API_KEY  - 공공데이터포털(data.go.kr) API용

카카오 키는 JavaScript 키와 REST API 키가 서로 다르다. 같은 앱이라도
dapi.kakao.com/v2/local/* 은 REST 키만 받고, JS 키를 쓰면 401이 난다.
(개발자 콘솔 > 내 애플리케이션 > 앱 키 에서 둘 다 확인 가능)

DB는 로컬 MySQL (DBeaver로 관리). 나중에 TiDB Cloud로 옮기게 되면
.env 값만 바꾸면 되도록 변수명을 범용(MYSQL_*)으로 잡아뒀다.
"""

import os

from dotenv import load_dotenv

load_dotenv()  # .env 파일을 환경변수로 로드


def _is_placeholder(value: str) -> bool:
    """<여기에_비밀번호> 같은 자리표시자는 값이 없는 것으로 본다.

    안 그러면 '설정은 됐는데 접속은 안 되는' 상태가 되어,
    DB 없이도 돌아가야 할 기능(로그인 등)이 폴백을 못 타고 그냥 죽는다.
    """
    v = value.strip()
    return v.startswith("<") and v.endswith(">")


def _setting(*names: str, default: str = "") -> str:
    """설정값을 여러 이름으로 찾아본다.

    1) 환경변수 / .env  — 로컬 개발
    2) st.secrets       — Streamlit Community Cloud 배포
                          (Cloud는 시크릿을 환경변수로 넣어주지 않는다)

    이름을 여러 개 받는 이유: .env 키를 MYSQL_HOST 로 적기도 하고
    TiDB 콘솔이 알려주는 DB_HOST 로 적기도 해서 둘 다 인식되게 했다.
    """
    for name in names:
        value = os.getenv(name)
        if value and not _is_placeholder(value):
            return value

    try:  # streamlit이 없는 환경(수집 스크립트 단독 실행)에서도 죽지 않게
        import streamlit as st

        for name in names:
            if name in st.secrets and not _is_placeholder(str(st.secrets[name])):
                return str(st.secrets[name])
    except Exception:  # noqa: BLE001
        pass

    return default


# ── DB (로컬 MySQL 또는 TiDB Cloud) ────────────────────────────
MYSQL_HOST = _setting("MYSQL_HOST", "DB_HOST")
MYSQL_PORT = int(_setting("MYSQL_PORT", "DB_PORT", default="3306"))
MYSQL_USER = _setting("MYSQL_USER", "DB_USERNAME", "DB_USER")
MYSQL_PASSWORD = _setting("MYSQL_PASSWORD", "DB_PASSWORD")
MYSQL_DATABASE = _setting("MYSQL_DATABASE", "DB_DATABASE", "DB_NAME")

# ── 지금 사용하는 API 키 ───────────────────────────────────────
KAKAO_JS_KEY = _setting("KAKAO_JS_KEY")  # 지도 표시 (JavaScript 키)
KAKAO_REST_KEY = _setting("KAKAO_REST_KEY")  # 주소 검색/지오코딩 (REST API 키)
DATA_GO_KR_API_KEY = _setting("DATA_GO_KR_API_KEY")

# ── 나중에 필요해지면 .env에 추가해서 쓰는 키 (없어도 앱은 동작) ──
# 서울 열린데이터광장(data.seoul.go.kr) - 종원 담당 CCTV Open API를 쓸 경우 필요
SEOUL_OPENAPI_KEY = _setting("SEOUL_OPENAPI_KEY")


def settings_report() -> list[dict]:
    """각 설정값이 '어디에서' 왔는지 점검 결과.

    배포하면 값이 안 보여서 "Secrets를 넣었는데 왜 안 되지"를 확인할 방법이 없다.
    이름과 출처(환경변수 / Secrets / 없음)만 돌려준다 — 값은 절대 담지 않는다.
    """
    checks = [
        ("DB_HOST", ("MYSQL_HOST", "DB_HOST")),
        ("DB_PORT", ("MYSQL_PORT", "DB_PORT")),
        ("DB_USERNAME", ("MYSQL_USER", "DB_USERNAME", "DB_USER")),
        ("DB_PASSWORD", ("MYSQL_PASSWORD", "DB_PASSWORD")),
        ("DB_DATABASE", ("MYSQL_DATABASE", "DB_DATABASE", "DB_NAME")),
        ("KAKAO_JS_KEY", ("KAKAO_JS_KEY",)),
        ("KAKAO_REST_KEY", ("KAKAO_REST_KEY",)),
        ("SEOUL_OPENAPI_KEY", ("SEOUL_OPENAPI_KEY",)),
    ]

    try:  # streamlit 없이 돌리는 스크립트에서도 죽지 않게
        import streamlit as st

        secret_names = set(st.secrets.keys())
    except Exception:  # noqa: BLE001
        secret_names = set()

    report = []
    for label, names in checks:
        source = "없음"
        for name in names:
            value = os.getenv(name)
            if value and not _is_placeholder(value):
                source = f"환경변수 {name}"
                break
            if name in secret_names:
                source = f"Secrets {name}"
                break
        report.append({"항목": label, "출처": source, "설정됨": source != "없음"})
    return report


def is_db_configured() -> bool:
    """DB에 실제로 접속할 수 있는 설정이 갖춰졌는지.

    호스트/사용자/DB명이 있어도 원격 DB에 비밀번호가 없으면 접속은 반드시 실패한다.
    그런 상태를 True로 보고하면 CSV 폴백이 있는 기능은 조용히 넘어가지만,
    폴백이 없는 기능(로그인)은 그대로 에러가 난다. 그래서 여기서 걸러낸다.
    (로컬 MySQL은 비밀번호가 비어 있는 경우가 흔해서 예외로 둔다.)
    """
    if not all([MYSQL_HOST, MYSQL_USER, MYSQL_DATABASE]):
        return False

    is_local = MYSQL_HOST in ("localhost", "127.0.0.1", "::1")
    return bool(MYSQL_PASSWORD) or is_local
