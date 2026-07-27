"""
공통 UI 유틸 - 모든 페이지에서 동일한 룩앤필을 쓰기 위한 헬퍼.

사용법 (각 페이지 상단):
    from common.ui import apply_style, hero

    st.set_page_config(...)
    apply_style()
    hero("🗺️", "지도 조회", "CCTV·금지구역·단속 다발구역을 한눈에")
"""

import streamlit as st

# 팀 컬러 팔레트 (페이지들이 공유)
PRIMARY = "#4361ee"
PRIMARY_DARK = "#3a0ca3"
ACCENT = "#f72585"
GREEN = "#2ec4b6"
AMBER = "#ff9f1c"
RED = "#e63946"
PURPLE = "#7209b7"

_GLOBAL_CSS = f"""
<style>
    /* 웹폰트 */
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css');

    html, body, [class*="css"], [data-testid="stAppViewContainer"] * {{
        font-family: 'Pretendard', -apple-system, 'Malgun Gothic', sans-serif;
    }}

    /* Material Symbols 아이콘은 위 폰트 규칙에서 제외한다.
       (제외하지 않으면 :material/xxx: 아이콘이 'settings' 같은 글자로 보인다)
       아이콘 종류마다 testid가 달라서(stExpanderIcon, stTooltipIcon …) 접미사로 함께 잡는다. */
    [data-testid="stIconMaterial"],
    [data-testid$="Icon"] {{
        font-family: 'Material Symbols Rounded' !important;
    }}

    /* 사이드바 */
    [data-testid="stSidebar"] {{
        background: linear-gradient(180deg, #f8f9ff 0%, #eef1fb 100%);
        border-right: 1px solid #e2e6f5;
    }}

    /* 메트릭 카드 */
    [data-testid="stMetric"] {{
        background: #ffffff;
        border: 1px solid #e8ebf7;
        border-radius: 14px;
        padding: 14px 18px;
        box-shadow: 0 2px 10px rgba(67, 97, 238, 0.06);
    }}
    [data-testid="stMetricLabel"] {{ color: #6b7280; }}
    [data-testid="stMetricValue"] {{ color: {PRIMARY_DARK}; }}

    /* expander (FAQ 등) */
    [data-testid="stExpander"] {{
        border: 1px solid #e8ebf7 !important;
        border-radius: 12px !important;
        box-shadow: 0 1px 6px rgba(67, 97, 238, 0.05);
        margin-bottom: 6px;
    }}

    /* 버튼 */
    .stButton > button {{
        border-radius: 10px;
        border: 1px solid {PRIMARY};
        color: {PRIMARY};
    }}
    .stButton > button:hover {{
        background: {PRIMARY};
        color: white;
    }}

    /* 히어로 배너 */
    .hero {{
        background: linear-gradient(120deg, {PRIMARY} 0%, {PRIMARY_DARK} 100%);
        border-radius: 18px;
        padding: 28px 32px;
        margin-bottom: 22px;
        color: white;
        box-shadow: 0 8px 24px rgba(58, 12, 163, 0.18);
    }}
    .hero h1 {{
        margin: 0 0 6px 0;
        font-size: 1.7rem;
        font-weight: 800;
        color: white;
    }}
    .hero p {{
        margin: 0;
        opacity: 0.85;
        font-size: 0.98rem;
    }}

    /* 기능 카드 (홈 화면) */
    .feature-card {{
        background: #ffffff;
        border: 1px solid #e8ebf7;
        border-radius: 16px;
        padding: 22px 20px;
        height: 100%;
        box-shadow: 0 2px 12px rgba(67, 97, 238, 0.07);
        transition: transform .15s ease, box-shadow .15s ease;
    }}
    .feature-card:hover {{
        transform: translateY(-3px);
        box-shadow: 0 8px 22px rgba(67, 97, 238, 0.14);
    }}
    .feature-card .icon {{ font-size: 1.9rem; }}
    .feature-card h3 {{
        margin: 8px 0 6px 0;
        font-size: 1.05rem;
        color: #1f2544;
    }}
    .feature-card p {{
        margin: 0;
        font-size: 0.85rem;
        color: #6b7280;
        line-height: 1.5;
    }}
    .feature-card .owner {{
        display: inline-block;
        margin-top: 12px;
        font-size: 0.72rem;
        font-weight: 700;
        color: {PRIMARY};
        background: #eef1fd;
        padding: 3px 10px;
        border-radius: 999px;
    }}

    /* 상태 칩 */
    .chip {{
        display: inline-block;
        font-size: 0.78rem;
        font-weight: 600;
        padding: 4px 12px;
        border-radius: 999px;
        margin-right: 8px;
        margin-bottom: 4px;
    }}
    .chip.ok  {{ background: #e6f9f5; color: #0f766e; border: 1px solid #99e8dc; }}
    .chip.bad {{ background: #fdeaea; color: #b91c1c; border: 1px solid #f5b5b5; }}
</style>
"""


def apply_style() -> None:
    """전역 CSS 주입. 각 페이지에서 st.set_page_config() 직후 1회 호출."""
    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)


def hero(emoji: str, title: str, subtitle: str) -> None:
    """페이지 상단 그라데이션 배너."""
    st.markdown(
        f"""
        <div class="hero">
            <h1>{emoji} {title}</h1>
            <p>{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def feature_card(emoji: str, title: str, desc: str, owner: str) -> str:
    """홈 화면 기능 소개 카드 HTML 반환 (st.markdown(unsafe_allow_html=True)로 렌더)."""
    return f"""
    <div class="feature-card">
        <div class="icon">{emoji}</div>
        <h3>{title}</h3>
        <p>{desc}</p>
        <span class="owner">{owner}</span>
    </div>
    """


def status_chip(label: str, ok: bool) -> str:
    """설정 상태 칩 HTML 반환."""
    icon = "✓" if ok else "✕"
    cls = "ok" if ok else "bad"
    return f'<span class="chip {cls}">{icon} {label}</span>'