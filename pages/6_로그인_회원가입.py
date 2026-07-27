"""
[담당: 승희] 로그인 · 회원가입 페이지.

로그인하면 st.session_state["user"]에 사용자 정보가 들어가고,
마이페이지(주차 등록·기록)에서 그 값을 사용한다.
계정 로직은 전부 common/auth.py에 있고 여기는 화면만 담당한다.
"""

import streamlit as st

from common.auth import current_user, login, logout, signup, storage_label
from common.ui import apply_style, hero

st.set_page_config(page_title="로그인 · 회원가입", page_icon="🔐", layout="centered")
apply_style()
hero("🔐", "로그인 · 회원가입", "로그인하면 주차 위치를 기록하고 다시 찾아볼 수 있어요. (담당: 승희)")

user = current_user()

# ── 이미 로그인한 경우 ────────────────────────────────────────
if user:
    st.success(f"**{user['username']}** 님으로 로그인되어 있습니다.")
    with st.container(horizontal=True):
        st.page_link("pages/7_마이페이지.py", label="마이페이지로 이동")
        if st.button("로그아웃"):
            logout()
            st.rerun()
    st.stop()

# ── 로그인 / 회원가입 ─────────────────────────────────────────
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
