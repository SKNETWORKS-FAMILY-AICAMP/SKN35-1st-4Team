"""
앗찻차! — 앱 진입점(라우터).

실행
    uv run streamlit run main.py

화면 자체는 app_pages/ 안에 있고, 이 파일은 어떤 페이지를 어떤 이름으로
사이드바에 보여줄지만 정한다.

왜 st.navigation 을 쓰나
    예전에는 pages/ 폴더를 그대로 두어 스트림릿이 파일명으로 메뉴를 만들었다.
    그러면 (1) 진입 화면이 'main' 이라는 파일명 그대로 뜨고,
    (2) 로그인·회원가입이 '둘러보기' 메뉴들과 나란히 붙어 버린다.
    로그인은 콘텐츠가 아니라 계정 상태라 같은 줄에 있으면 안 맞는다.

    지금은 메뉴를 두 묶음으로 나누고, 로그인 여부에 따라
    '로그인' 과 '내 주차 기록' 중 하나만 보여준다.
"""

import streamlit as st

from common.auth import current_user, logout
from common.ui import apply_style, brand_header

st.set_page_config(
    page_title="앗찻차! 주정차 알림",
    page_icon="assets/atchacha_icon.svg",
    layout="wide",
)
apply_style()

with st.sidebar:
    brand_header()

user = current_user()

home = st.Page(
    "app_pages/home.py", title="홈", icon=":material/home:", default=True
)
faq = st.Page("app_pages/faq.py", title="자주 묻는 질문", icon=":material/help:")
board = st.Page("app_pages/board.py", title="민원 사례", icon=":material/forum:")
mypage = st.Page(
    "app_pages/mypage.py", title="내 주차 기록", icon=":material/directions_car:"
)
login = st.Page("app_pages/login.py", title="로그인", icon=":material/login:")

pages = {
    "둘러보기": [home, faq, board],
    "내 계정": [mypage] if user else [login],
}

# 로그인했으면 사이드바 맨 위에 누구인지와 로그아웃을 둔다.
# 메뉴 항목으로 만들면 '페이지'처럼 보여서 헷갈린다.
if user:
    with st.sidebar:
        with st.container(horizontal=True, vertical_alignment="center"):
            st.markdown(f"**{user['username']}** 님", width="stretch")
            if st.button("로그아웃", icon=":material/logout:", width="content"):
                logout()
                st.rerun()

st.navigation(pages).run()
