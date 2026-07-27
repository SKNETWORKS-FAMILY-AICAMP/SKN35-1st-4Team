"""
[담당: 승희] 로그인 · 회원가입 페이지.

로그인하면 st.session_state["user"]에 사용자 정보가 들어가고,
마이페이지(주차 등록·기록)에서 그 값을 사용한다.
계정 로직은 전부 common/auth.py에 있고 여기는 화면만 담당한다.
"""

import streamlit as st

from common.auth import current_user, login, signup, storage_label
from common.ui import MARK_LOCK, empty_state, hero

hero(MARK_LOCK, "로그인 · 회원가입",
     "로그인하면 주차한 자리를 기록하고, 아낀 과태료를 모아볼 수 있어요.")

# 로그인하면 라우터(main.py)가 이 페이지를 메뉴에서 빼고 '내 주차 기록'으로 바꾼다.
# 그래도 주소로 직접 들어올 수 있으니 안내만 남긴다.
if current_user():
    st.success(
        "이미 로그인되어 있습니다. 왼쪽 **내 주차 기록**에서 이어서 이용하세요.",
        icon=":material/check_circle:",
    )
    st.stop()

# ── 로그인 / 회원가입 ─────────────────────────────────────────
art, form = st.columns([1, 1], vertical_alignment="center")

with art:
    empty_state(
        "lock",
        "내 주차 기록, 안전하게",
        "비밀번호는 해시로만 저장하고 평문은 남기지 않습니다.",
    )

with form:
    tab_login, tab_signup = st.tabs(["로그인", "회원가입"])

    with tab_login:
        with st.form("login_form"):
            username = st.text_input("아이디", key="login_username")
            password = st.text_input("비밀번호", type="password", key="login_password")
            submitted = st.form_submit_button("로그인", type="primary")

        if submitted:
            ok, message = login(username, password)
            if ok:
                st.success(message)
                st.rerun()
            else:
                st.error(message)

    with tab_signup:
        with st.form("signup_form"):
            new_username = st.text_input(
                "아이디", help="영문·숫자·밑줄 3~20자", key="signup_username"
            )
            new_password = st.text_input(
                "비밀번호", type="password", help="8자 이상", key="signup_password"
            )
            new_password2 = st.text_input(
                "비밀번호 확인", type="password", key="signup_password2"
            )
            signup_submitted = st.form_submit_button("가입하기", type="primary")

        if signup_submitted:
            ok, message = signup(new_username, new_password, new_password2)
            if ok:
                st.success(message)
            else:
                st.error(message)

st.caption(
    "비밀번호는 pbkdf2-sha256으로 해시해서 저장하며 평문은 남기지 않습니다. "
    f"저장소: {storage_label()}"
)
