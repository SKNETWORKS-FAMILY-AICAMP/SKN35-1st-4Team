"""
'앗찻차!' 디자인 시스템 — 모든 페이지가 공유하는 룩앤필.

사용법 (각 페이지 상단):
    from common.ui import apply_style, hero, section

    st.set_page_config(...)
    apply_style()
    hero(MARK_ALERT, "제목", "부제")
    section("주차 등록", "어디에 세웠는지 남겨두세요")

브랜드
    앗찻차! — "앗, 여기 세우면 안 되는 곳이었네" 하고 알아채는 순간을 잡아주는 서비스.
    톤은 밝고 가볍게. 다만 불법주정차를 부추기지 않는다. 겁주기보다
    "합법 주차장이 이만큼 싸다"를 보여주는 쪽으로 문구를 쓴다.

그림에 관하여 (중요)
    st.html 은 DOMPurify 로 내용을 걸러내는데 인라인 svg 태그가 통째로 지워진다.
    그래서 모든 그림은 svg_img() 로 data URI 이미지로 만들어 넣는다.
    움직임도 SVG 문서 안에 style 로 넣어야 한다 (바깥 CSS는 안쪽에 닿지 않는다).

    또 하나: 이 파일의 CSS 안에 꺾쇠 태그 문자열을 적으면 DOMPurify 가
    스타일 블록을 통째로 지워서 앱 디자인이 전부 날아간다. 주석에도 쓰지 말 것.

색은 .streamlit/config.toml 의 테마와 짝이다. 한쪽만 바꾸면 어긋난다.
"""

from __future__ import annotations

import base64
import math
from pathlib import Path

import streamlit as st

# ── 브랜드 팔레트 ────────────────────────────────────────────────
BRAND = "#D14314"        # 앗찻차 코랄 (primaryColor)
BRAND_LIGHT = "#FF8A3D"  # 그라데이션 밝은 쪽
BRAND_DEEP = "#8A2B0B"   # 그라데이션 어두운 쪽 / 제목
BRAND_SOFT = "#FFF1E8"   # 아주 옅은 코랄 면
INK = "#26201D"          # 본문
MUTED = "#6B625C"        # 보조 텍스트
LINE = "#EFE1D7"         # 테두리
SURFACE = "#FFFFFF"
TINT = "#FFF6F0"

GREEN = "#0E9F6E"        # 공영 / 안전 / 절약
AMBER = "#E07B00"        # 민영 / 주의
RED = "#D92D20"          # 단속 / 위험
PURPLE = "#7048E8"       # CCTV
BLUE = "#3B5BDB"         # 내 위치
PINK = "#D6336C"         # 내 주차 기록

# 예전 이름으로 import 하는 팀원 페이지가 있어 별칭을 남겨둔다
PRIMARY = BRAND
PRIMARY_DARK = BRAND_DEEP
ACCENT = PINK

ROOT = Path(__file__).resolve().parent.parent
LOGO = ROOT / "assets/atchacha_logo.svg"
ICON = ROOT / "assets/atchacha_icon.svg"

_SVG_NS = 'xmlns="http://www.w3.org/2000/svg"'
_FONT = "Pretendard, -apple-system, 'Malgun Gothic', sans-serif"


def svg_img(svg: str, width: int, height: int, cls: str = "", alt: str = "") -> str:
    """SVG를 img 태그 문자열로 감싼다.

    st.html 은 인라인 svg 를 지운다. data URI 이미지는 그대로 통과한다.
    바깥 CSS가 SVG 안쪽에 닿지 않으므로 움직임은 SVG 안에 넣어야 한다.
    """
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    class_attr = f' class="{cls}"' if cls else ""
    return (
        f'<img{class_attr} src="data:image/svg+xml;base64,{encoded}" '
        f'width="{width}" height="{height}" alt="{alt}">'
    )


def _data_uri(svg: str) -> str:
    """CSS background-image 로 쓸 data URI."""
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")


# 히어로 배경에 깔리는 점 패턴 — 단색 그라데이션보다 깊이가 생긴다
_DOTS = _data_uri(
    f'<svg {_SVG_NS} width="26" height="26" viewBox="0 0 26 26">'
    '<circle cx="3" cy="3" r="1.4" fill="rgba(255,255,255,.20)"/>'
    '<circle cx="16" cy="16" r="1.4" fill="rgba(255,255,255,.14)"/>'
    "</svg>"
)

_GLOBAL_CSS = f"""
<style>
    /* ══ 사이드바 ══════════════════════════════════════════════ */
    [data-testid="stSidebar"] {{
        background: linear-gradient(180deg, #FFF9F5 0%, #FDEDE3 100%);
        border-right: 1px solid {LINE};
    }}
    [data-testid="stSidebar"] .stMarkdown strong {{
        color: {BRAND_DEEP};
        font-size: .82rem;
        letter-spacing: .02em;
    }}
    /* 사이드바 브랜드 블록 */
    .brand {{
        padding: 2px 0 14px;
        border-bottom: 1px solid {LINE};
        margin-bottom: 10px;
        animation: atc-rise .5s cubic-bezier(.22,1,.36,1) both;
    }}
    .brand img {{ display: block; }}
    .brand-tag {{
        margin-top: 7px; font-size: .78rem; color: {MUTED}; font-weight: 600;
    }}

    /* ══ 진입 애니메이션 ═══════════════════════════════════════ */
    @keyframes atc-rise {{
        from {{ opacity: 0; transform: translateY(10px); }}
        to   {{ opacity: 1; transform: translateY(0); }}
    }}
    @keyframes atc-pop {{
        0%   {{ transform: scale(.85); opacity: 0; }}
        62%  {{ transform: scale(1.05); opacity: 1; }}
        100% {{ transform: scale(1); opacity: 1; }}
    }}
    @keyframes atc-shimmer {{
        0%   {{ transform: translateX(-120%) skewX(-18deg); }}
        100% {{ transform: translateX(320%) skewX(-18deg); }}
    }}
    @keyframes atc-coin-fall {{
        0%   {{ transform: translateY(-14px) rotate(0deg);   opacity: 0; }}
        18%  {{ opacity: .95; }}
        100% {{ transform: translateY(104px) rotate(220deg); opacity: 0; }}
    }}

    /* ══ 히어로 ════════════════════════════════════════════════ */
    .hero {{
        position: relative;
        overflow: hidden;
        border-radius: 20px;
        padding: 26px 30px;
        margin-bottom: 18px;
        color: #fff;
        background:
            url("{_DOTS}"),
            radial-gradient(120% 160% at 88% -30%, rgba(255,255,255,.30) 0%, rgba(255,255,255,0) 55%),
            linear-gradient(118deg, {BRAND_LIGHT} 0%, {BRAND} 52%, {BRAND_DEEP} 100%);
        box-shadow: 0 14px 34px rgba(138, 43, 11, .26);
        animation: atc-rise .5s cubic-bezier(.22,1,.36,1) both;
    }}
    /* 배너 위를 한 번 스쳐 지나가는 빛 */
    .hero::before {{
        content: "";
        position: absolute; top: 0; bottom: 0; left: 0;
        width: 28%;
        background: linear-gradient(90deg, rgba(255,255,255,0) 0%,
                    rgba(255,255,255,.26) 50%, rgba(255,255,255,0) 100%);
        animation: atc-shimmer 3.6s ease-in-out 1.1s 2;
        pointer-events: none;
    }}
    .hero-row {{ display: flex; align-items: center; gap: 16px; position: relative; z-index: 1; }}
    @keyframes atc-wobble {{
        0%, 88%, 100% {{ transform: rotate(0deg) scale(1); }}
        91%  {{ transform: rotate(-11deg) scale(1.08); }}
        94%  {{ transform: rotate(9deg)  scale(1.08); }}
        97%  {{ transform: rotate(-4deg) scale(1.02); }}
    }}
    .hero-mark {{
        flex: 0 0 auto; display: flex;
        filter: drop-shadow(0 4px 10px rgba(0,0,0,.18));
        animation: atc-wobble 6s ease-in-out infinite;
    }}
    .hero h1 {{
        margin: 0 0 5px 0; font-size: 1.6rem; font-weight: 800;
        color: #fff; letter-spacing: -.5px; line-height: 1.25;
    }}
    .hero p {{ margin: 0; opacity: .93; font-size: .95rem; line-height: 1.5; }}
    .hero-chips {{ margin-top: 12px; display: flex; flex-wrap: wrap; gap: 8px; }}
    .hero-chip {{
        display: inline-flex; align-items: center; gap: 6px;
        background: rgba(255,255,255,.18);
        border: 1px solid rgba(255,255,255,.34);
        border-radius: 999px; padding: 5px 13px;
        font-size: .8rem; font-weight: 700;
        backdrop-filter: blur(3px);
    }}
    .hero-chip b {{ font-weight: 800; }}

    /* ══ 섹션 헤더 ═════════════════════════════════════════════ */
    .sec {{ display: flex; align-items: flex-start; gap: 11px; margin: 22px 0 10px; }}
    .sec-bar {{
        flex: 0 0 auto; width: 5px; height: 34px; border-radius: 3px; margin-top: 2px;
        background: linear-gradient(180deg, {BRAND_LIGHT}, {BRAND});
    }}
    .sec h2 {{
        margin: 0; font-size: 1.16rem; font-weight: 800;
        color: {INK}; letter-spacing: -.3px;
    }}
    .sec p {{ margin: 2px 0 0; font-size: .85rem; color: {MUTED}; }}

    /* ══ 메트릭 카드 ═══════════════════════════════════════════ */
    [data-testid="stMetric"] {{
        background: {SURFACE};
        border: 1px solid {LINE};
        border-radius: 16px;
        padding: 15px 18px;
        box-shadow: 0 2px 10px rgba(209, 67, 20, .06);
        transition: box-shadow .2s ease, transform .2s ease, border-color .2s ease;
        animation: atc-rise .45s cubic-bezier(.22,1,.36,1) both;
    }}
    [data-testid="stMetric"]:hover {{
        transform: translateY(-3px);
        border-color: #F6C8B0;
        box-shadow: 0 12px 26px rgba(209, 67, 20, .16);
    }}
    [data-testid="stMetricLabel"] {{ color: {MUTED}; font-weight: 600; }}
    [data-testid="stMetricValue"] {{ color: {BRAND_DEEP}; font-weight: 800; }}
    /* 카드가 좁으면 값이 잘린다. 폭에 맞춰 줄이고 그래도 길면 줄바꿈.
       Streamlit 이 값 안쪽에 한 겹 더 감싸는 경우가 있어 자손까지 함께 푼다. */
    [data-testid="stMetricValue"],
    [data-testid="stMetricValue"] * {{
        white-space: normal !important;
        overflow: visible !important;
        text-overflow: clip !important;
        overflow-wrap: anywhere;
    }}
    [data-testid="stMetricValue"] > div {{
        font-size: clamp(1.05rem, 1.9vw, 2.1rem);
        line-height: 1.25;
    }}

    /* ══ 컨테이너·expander ════════════════════════════════════ */
    [data-testid="stExpander"] {{
        border: 1px solid {LINE} !important;
        border-radius: 14px !important;
        box-shadow: 0 1px 6px rgba(209, 67, 20, .05);
        margin-bottom: 6px;
        overflow: hidden;
    }}
    [data-testid="stVerticalBlockBorderWrapper"] {{ border-radius: 16px; }}

    /* ══ 버튼 ══════════════════════════════════════════════════ */
    .stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {{
        border-radius: 11px;
        font-weight: 700;
        transition: transform .14s ease, box-shadow .18s ease;
    }}
    .stButton > button:hover, .stDownloadButton > button:hover,
    .stFormSubmitButton > button:hover {{
        transform: translateY(-1px);
        box-shadow: 0 6px 16px rgba(209, 67, 20, .22);
    }}

    /* ══ 탭 ════════════════════════════════════════════════════ */
    [data-baseweb="tab-list"] {{ gap: 6px; }}
    [data-baseweb="tab"] {{ font-weight: 700; }}

    /* ══ 절약 배너 (지도 아래) ════════════════════════════════ */
    .save-banner {{
        position: relative;
        overflow: hidden;
        border-radius: 18px;
        padding: 17px 24px;
        margin: 4px 0 12px;
        border: 1px solid #FBD8C4;
        background: linear-gradient(100deg, #FFF7F2 0%, #FFEFE4 100%);
        box-shadow: 0 6px 18px rgba(209, 67, 20, .10);
        animation: atc-pop .44s cubic-bezier(.22,1.2,.36,1) both;
    }}
    .save-banner.is-safe {{
        border-color: #BDEBD8;
        background: linear-gradient(100deg, #F3FCF8 0%, #E6F8F0 100%);
        box-shadow: 0 6px 18px rgba(14, 159, 110, .10);
    }}
    .save-row {{
        position: relative; z-index: 1;
        display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px 14px;
    }}
    .save-lede {{ font-size: 1.12rem; font-weight: 800; color: {BRAND_DEEP}; }}
    .save-banner.is-safe .save-lede {{ color: #0B6B4B; }}
    .save-amt {{
        font-size: 2rem; font-weight: 900; color: {BRAND};
        letter-spacing: -1px; line-height: 1.1;
    }}
    .save-banner.is-safe .save-amt {{ color: {GREEN}; }}
    .save-sub {{ position: relative; z-index: 1;
                 font-size: .86rem; color: {MUTED}; margin-top: 5px; }}
    .save-sub b {{ color: {INK}; }}
    .save-coin {{
        position: absolute; top: -10px; z-index: 0;
        opacity: 0; pointer-events: none;
        animation: atc-coin-fall 2.6s ease-in infinite;
    }}

    /* ══ 누적 절약 리포트 ═════════════════════════════════════ */
    .saved-report {{
        display: flex; align-items: center; gap: 15px;
        border: 1px solid #BDEBD8; border-radius: 16px;
        background: linear-gradient(100deg, #F3FCF8 0%, #E6F8F0 100%);
        padding: 15px 20px; margin: 2px 0 12px;
        animation: atc-rise .45s cubic-bezier(.22,1,.36,1) both;
    }}
    .saved-report .big {{
        font-size: 1.5rem; font-weight: 900; color: {GREEN}; letter-spacing: -.5px;
    }}
    .saved-report .cap {{ font-size: .84rem; color: {MUTED}; }}

    /* ══ 빈 상태 ═══════════════════════════════════════════════ */
    .empty-state {{
        text-align: center;
        padding: 20px 16px 24px;
        border: 1px dashed #F0CDB8;
        border-radius: 18px;
        background: linear-gradient(180deg, {TINT} 0%, #FFFDFB 100%);
        animation: atc-rise .45s cubic-bezier(.22,1,.36,1) both;
    }}
    .empty-state h3 {{
        margin: 8px 0 4px; font-size: 1.02rem; font-weight: 800; color: {INK};
    }}
    .empty-state p {{ margin: 0; font-size: .86rem; color: {MUTED}; }}

    /* ══ 주차장 카드 ═══════════════════════════════════════════ */
    .lot-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(268px, 1fr));
        gap: 14px;
        margin: 6px 0 14px;
    }}
    .lot {{
        position: relative;
        overflow: hidden;
        background: {SURFACE};
        border: 1px solid {LINE};
        border-radius: 18px;
        padding: 16px 18px 14px 22px;
        box-shadow: 0 2px 12px rgba(209, 67, 20, .06);
        transition: transform .16s ease, box-shadow .16s ease, border-color .16s ease;
        animation: atc-rise .45s cubic-bezier(.22,1,.36,1) both;
    }}
    .lot:hover {{
        transform: translateY(-4px);
        border-color: #F6C8B0;
        box-shadow: 0 14px 30px rgba(209, 67, 20, .17);
    }}
    /* 왼쪽 색 띠로 공영·민영을 한눈에 */
    .lot::before {{
        content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 6px;
        background: var(--edge, {BRAND});
    }}
    .lot-rank {{
        position: absolute; top: 12px; right: 14px;
        font-size: .72rem; font-weight: 800; color: {BRAND};
        background: {TINT}; border-radius: 999px; padding: 3px 9px;
    }}
    .lot-name {{
        font-size: 1.01rem; font-weight: 800; color: {INK};
        line-height: 1.35; margin: 0 46px 6px 0;
        overflow-wrap: anywhere;
    }}
    .lot-tags {{ display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 10px; }}
    .lot-tag {{
        font-size: .72rem; font-weight: 700; border-radius: 999px;
        padding: 2px 9px; background: {BRAND_SOFT}; color: {BRAND_DEEP};
    }}
    .lot-fee {{
        font-size: 1.42rem; font-weight: 900; color: {BRAND_DEEP};
        letter-spacing: -.6px; line-height: 1.1;
    }}
    .lot-fee small {{ font-size: .74rem; font-weight: 700; color: {MUTED}; margin-left: 5px; }}
    .lot-rows {{ margin-top: 10px; display: grid; gap: 5px; }}
    .lot-row {{ display: flex; justify-content: space-between; gap: 10px; font-size: .82rem; }}
    /* 라벨이 '운 영' 처럼 세로로 쪼개지지 않게 */
    .lot-row span:first-child {{ color: {MUTED}; white-space: nowrap; flex: 0 0 auto; }}
    .lot-row span:last-child {{ color: {INK}; font-weight: 600; text-align: right; }}
    .lot-fee.unknown {{ font-size: 1.02rem; color: {MUTED}; font-weight: 700; }}
    .lot-bar {{
        margin-top: 9px; height: 7px; border-radius: 4px;
        background: #F3E7DE; overflow: hidden;
    }}
    .lot-bar i {{ display: block; height: 100%; border-radius: 4px;
                  background: linear-gradient(90deg, {BRAND_LIGHT}, {BRAND}); }}

    /* ══ 지도 범례 ═════════════════════════════════════════════ */
    .legend {{
        display: flex; flex-wrap: wrap; gap: 8px 18px; align-items: center;
        border: 1px solid {LINE}; border-radius: 14px;
        background: {SURFACE}; padding: 11px 16px; margin: 4px 0 10px;
    }}
    .legend-item {{ display: inline-flex; align-items: center; gap: 7px;
                    font-size: .82rem; color: {INK}; font-weight: 600; }}
    .legend-item small {{ color: {MUTED}; font-weight: 500; }}
    .legend-heat {{ display: inline-block; width: 74px; height: 10px; border-radius: 5px;
                    background: linear-gradient(90deg, #FFCBAC, #FF8F5C, #DE5722, #9E360D); }}

    /* ══ 푸터 ══════════════════════════════════════════════════ */
    .foot {{
        margin: 26px 0 6px; padding: 16px 20px;
        border-top: 1px solid {LINE};
        color: {MUTED}; font-size: .8rem; line-height: 1.7;
    }}
    .foot b {{ color: {BRAND_DEEP}; }}

    /* ══ 기능 카드 ═════════════════════════════════════════════ */
    .feature-card {{
        background: {SURFACE};
        border: 1px solid {LINE};
        border-radius: 18px;
        padding: 22px 20px;
        height: 100%;
        box-shadow: 0 2px 12px rgba(209, 67, 20, .07);
        transition: transform .16s ease, box-shadow .16s ease;
    }}
    .feature-card:hover {{
        transform: translateY(-4px);
        box-shadow: 0 12px 26px rgba(209, 67, 20, .16);
    }}
    .feature-card .icon {{ font-size: 1.9rem; }}
    .feature-card h3 {{ margin: 8px 0 6px 0; font-size: 1.05rem; color: {INK}; }}
    .feature-card p {{ margin: 0; font-size: .85rem; color: {MUTED}; line-height: 1.5; }}
    .feature-card .owner {{
        display: inline-block; margin-top: 12px;
        font-size: .72rem; font-weight: 700; color: {BRAND};
        background: {TINT}; padding: 3px 10px; border-radius: 999px;
    }}

    /* ══ 상태 칩 ═══════════════════════════════════════════════ */
    .chip {{
        display: inline-block; font-size: .78rem; font-weight: 600;
        padding: 4px 12px; border-radius: 999px;
        margin-right: 8px; margin-bottom: 4px;
    }}
    .chip.ok  {{ background: #E6F8F0; color: #0B6B4B; border: 1px solid #A7E3CB; }}
    .chip.bad {{ background: #FDECEA; color: #A31910; border: 1px solid #F5B5B0; }}

    /* ══ 접근성 ════════════════════════════════════════════════ */
    @media (prefers-reduced-motion: reduce) {{
        .hero, .hero::before, .hero-mark, .save-banner, .save-coin,
        .saved-report, .empty-state, [data-testid="stMetric"] {{
            animation: none !important;
            transition: none !important;
        }}
    }}
</style>
"""


def apply_style() -> None:
    """전역 CSS 주입 + 사이드바 로고. 각 페이지에서 set_page_config() 직후 1회 호출."""
    st.html(_GLOBAL_CSS)
    if LOGO.exists():
        # size="medium" 이면 94x24px 짜리 조각으로 줄어들어 워드마크가 안 읽힌다.
        st.logo(str(LOGO), icon_image=str(ICON) if ICON.exists() else None, size="large")


def brand_header() -> None:
    """사이드바 맨 위 브랜드 블록.

    st.logo 는 헤더 높이에 맞춰 많이 축소돼서 로고가 잘 안 보인다.
    사이드바 본문에 큼직하게 한 번 더 둔다.
    """
    if not LOGO.exists():
        return
    st.html(
        f"""
        <div class="brand">
          {svg_img(LOGO.read_text(encoding="utf-8"), 176, 47, alt="앗찻차")}
          <div class="brand-tag">여기 세워도 될까? 3초 만에 확인</div>
        </div>
        """
    )


# ═══════════════════════════════════════════════════════════════
# 히어로 마크 (페이지마다 다른 그림)
# ═══════════════════════════════════════════════════════════════
def _mark(body: str) -> str:
    return (
        f'<svg {_SVG_NS} viewBox="0 0 64 64" width="44" height="44">'
        '<circle cx="32" cy="32" r="30" fill="rgba(255,255,255,.20)"/>'
        '<circle cx="32" cy="32" r="30" fill="none" stroke="rgba(255,255,255,.55)"'
        ' stroke-width="2.5"/>'
        f"{body}</svg>"
    )


MARK_ALERT = _mark(  # 앗! — 느낌표
    '<rect x="28" y="15" width="8" height="24" rx="4" fill="#fff"/>'
    '<circle cx="32" cy="47" r="5" fill="#fff"/>'
)
MARK_CHAT = _mark(  # FAQ — 말풍선 + 물음표
    '<path d="M16 20h32a4 4 0 0 1 4 4v18a4 4 0 0 1-4 4H30l-9 8v-8h-5a4 4 0 0 1-4-4V24'
    'a4 4 0 0 1 4-4z" fill="#fff"/>'
    '<path d="M28.5 29.5a3.8 3.8 0 1 1 5.2 3.5c-1.3.6-1.8 1.4-1.8 2.6" fill="none"'
    f' stroke="{BRAND}" stroke-width="2.6" stroke-linecap="round"/>'
    f'<circle cx="32" cy="40" r="1.9" fill="{BRAND}"/>'
)
MARK_BOARD = _mark(  # 민원 — 서류
    '<rect x="18" y="14" width="28" height="36" rx="4" fill="#fff"/>'
    f'<rect x="24" y="22" width="16" height="3" rx="1.5" fill="{BRAND}"/>'
    f'<rect x="24" y="30" width="16" height="3" rx="1.5" fill="{BRAND}" opacity=".65"/>'
    f'<rect x="24" y="38" width="10" height="3" rx="1.5" fill="{BRAND}" opacity=".45"/>'
)
MARK_LOCK = _mark(  # 로그인 — 자물쇠
    '<rect x="19" y="30" width="26" height="20" rx="5" fill="#fff"/>'
    '<path d="M25 30v-6a7 7 0 0 1 14 0v6" fill="none" stroke="#fff" stroke-width="4.5"'
    ' stroke-linecap="round"/>'
    f'<circle cx="32" cy="39" r="3.2" fill="{BRAND}"/>'
    f'<rect x="30.7" y="40" width="2.6" height="6" rx="1.3" fill="{BRAND}"/>'
)
MARK_CAR = _mark(  # 마이페이지 — 자동차
    '<path d="M17 40l3-11a5 5 0 0 1 4.8-3.6h14.4A5 5 0 0 1 44 29l3 11z" fill="#fff"/>'
    '<rect x="15" y="38" width="34" height="8" rx="4" fill="#fff"/>'
    f'<circle cx="24" cy="46" r="4" fill="{BRAND_DEEP}"/>'
    f'<circle cx="40" cy="46" r="4" fill="{BRAND_DEEP}"/>'
)


def hero(icon: str, title: str, subtitle: str, chips: list[str] | None = None) -> None:
    """페이지 상단 그라데이션 배너.

    icon 은 이모지도 되고 SVG 문자열도 된다 (팀원 페이지들이 이모지를 넘긴다).
    SVG 는 그대로 넣으면 st.html 이 걷어내므로 이미지로 바꿔 넣는다.
    chips 를 주면 배너 안에 요약 숫자를 알약 모양으로 붙인다.
    """
    mark = svg_img(icon, 44, 44, alt="") if icon.lstrip().startswith("<svg") else icon
    chips_html = ""
    if chips:
        items = "".join(f'<span class="hero-chip">{c}</span>' for c in chips)
        chips_html = f'<div class="hero-chips">{items}</div>'

    st.html(
        f"""
        <div class="hero">
          <div class="hero-row">
            <div class="hero-mark">{mark}</div>
            <div>
              <h1>{title}</h1>
              <p>{subtitle}</p>
            </div>
          </div>
          {chips_html}
        </div>
        """
    )


def section(title: str, subtitle: str = "") -> None:
    """섹션 제목. st.subheader 보다 눈에 띄고 페이지마다 리듬이 생긴다."""
    st.html(
        f"""
        <div class="sec">
          <div class="sec-bar"></div>
          <div>
            <h2>{title}</h2>
            {f"<p>{subtitle}</p>" if subtitle else ""}
          </div>
        </div>
        """
    )


# ═══════════════════════════════════════════════════════════════
# 일러스트 (빈 상태 등)
# ═══════════════════════════════════════════════════════════════
_ART_STYLE = f"""
  <style>
    text {{ font-family: {_FONT}; }}
    .float {{ animation: fl 3.4s ease-in-out infinite; }}
    .pop   {{ animation: pp 3.4s ease-in-out infinite; }}
    .draw  {{ animation: dw 1.5s ease-out; }}
    @keyframes fl {{ 0%,100% {{ transform: translateY(0); }}
                     50%     {{ transform: translateY(-7px); }} }}
    @keyframes pp {{ 0%,60%,100% {{ transform: scale(1); }}
                     72%         {{ transform: scale(1.14); }} }}
    @keyframes dw {{ from {{ stroke-dasharray: 300; stroke-dashoffset: 300; }}
                     to   {{ stroke-dasharray: 300; stroke-dashoffset: 0; }} }}
    @media (prefers-reduced-motion: reduce) {{
      .float, .pop, .draw {{ animation: none; }}
    }}
  </style>
"""


def _art_sign_car() -> str:
    """금지 표지판 앞에서 멈칫하는 자동차 — 홈 빈 상태."""
    return f"""<svg {_SVG_NS} viewBox="0 0 300 140" width="300" height="140">
  {_ART_STYLE}
  <ellipse cx="150" cy="126" rx="108" ry="8" fill="{LINE}" opacity=".75"/>
  <rect x="146" y="48" width="7" height="62" rx="3.5" fill="#B9AEA6"/>
  <circle cx="150" cy="44" r="27" fill="#fff" stroke="{RED}" stroke-width="7"/>
  <text x="150" y="54" text-anchor="middle" font-size="27" font-weight="800"
        fill="{BLUE}">P</text>
  <line x1="131" y1="63" x2="169" y2="25" stroke="{RED}" stroke-width="7"
        stroke-linecap="round"/>
  <g class="float">
    <path d="M32 106 L38 84 Q40 77 48 77 L96 77 Q104 77 108 84 L116 106 Z" fill="{BRAND}"/>
    <rect x="26" y="103" width="96" height="15" rx="7.5" fill="{BRAND_DEEP}"/>
    <path d="M47 82 L92 82 Q97 82 100 88 L103 94 L44 94 L46 88 Z" fill="#FFE3D0"/>
    <circle cx="47" cy="118" r="9" fill="{INK}"/><circle cx="47" cy="118" r="3.4" fill="#fff"/>
    <circle cx="101" cy="118" r="9" fill="{INK}"/><circle cx="101" cy="118" r="3.4" fill="#fff"/>
  </g>
  <g class="pop" style="transform-origin:210px 46px">
    <circle cx="210" cy="46" r="22" fill="{TINT}" stroke="{BRAND}" stroke-width="2.5"/>
    <text x="210" y="54" text-anchor="middle" font-size="19" font-weight="800"
          fill="{BRAND}">앗!</text>
  </g>
</svg>"""


def _art_lock() -> str:
    """열쇠와 자물쇠 — 로그인."""
    return f"""<svg {_SVG_NS} viewBox="0 0 300 140" width="300" height="140">
  {_ART_STYLE}
  <ellipse cx="150" cy="128" rx="92" ry="7" fill="{LINE}" opacity=".7"/>
  <g class="float">
    <rect x="106" y="58" width="76" height="58" rx="14" fill="{BRAND}"/>
    <path d="M122 58V42a22 22 0 0 1 44 0v16" fill="none" stroke="{BRAND_DEEP}"
          stroke-width="11" stroke-linecap="round"/>
    <circle cx="144" cy="82" r="9" fill="#FFE3D0"/>
    <rect x="140" y="86" width="8" height="17" rx="4" fill="#FFE3D0"/>
  </g>
  <g class="pop" style="transform-origin:216px 74px">
    <circle cx="216" cy="74" r="15" fill="none" stroke="{AMBER}" stroke-width="6"/>
    <rect x="228" y="70" width="38" height="8" rx="4" fill="{AMBER}"/>
    <rect x="252" y="78" width="7" height="11" rx="3.5" fill="{AMBER}"/>
    <rect x="262" y="78" width="7" height="8" rx="3.5" fill="{AMBER}"/>
  </g>
</svg>"""


def _art_garage() -> str:
    """차고 안의 자동차 — 주차 기록 없음."""
    return f"""<svg {_SVG_NS} viewBox="0 0 300 140" width="300" height="140">
  {_ART_STYLE}
  <ellipse cx="150" cy="128" rx="104" ry="7" fill="{LINE}" opacity=".7"/>
  <path d="M64 66 L150 26 L236 66 V118 H64 Z" fill="{BRAND_SOFT}" stroke="{BRAND}"
        stroke-width="3" stroke-linejoin="round"/>
  <path d="M64 66 L150 26 L236 66" fill="none" stroke="{BRAND}" stroke-width="5"
        stroke-linecap="round" stroke-linejoin="round" class="draw"/>
  <g class="float">
    <path d="M104 106 L109 88 Q111 82 118 82 L182 82 Q189 82 191 88 L196 106 Z"
          fill="{BRAND}"/>
    <rect x="99" y="103" width="102" height="14" rx="7" fill="{BRAND_DEEP}"/>
    <path d="M118 86 L182 86 Q186 86 188 91 L190 96 L110 96 L113 91 Z" fill="#FFE3D0"/>
    <circle cx="122" cy="117" r="8" fill="{INK}"/><circle cx="122" cy="117" r="3" fill="#fff"/>
    <circle cx="178" cy="117" r="8" fill="{INK}"/><circle cx="178" cy="117" r="3" fill="#fff"/>
  </g>
  <text x="150" y="60" text-anchor="middle" font-size="21" font-weight="800"
        fill="{BRAND}">P</text>
</svg>"""


def _art_search() -> str:
    """돋보기 — 검색 결과 없음."""
    return f"""<svg {_SVG_NS} viewBox="0 0 300 140" width="300" height="140">
  {_ART_STYLE}
  <ellipse cx="150" cy="128" rx="84" ry="7" fill="{LINE}" opacity=".7"/>
  <g class="float">
    <circle cx="136" cy="62" r="38" fill="{BRAND_SOFT}" stroke="{BRAND}" stroke-width="7"/>
    <rect x="166" y="88" width="46" height="13" rx="6.5" fill="{BRAND_DEEP}"
          transform="rotate(42 166 88)"/>
    <path d="M120 62h32" stroke="{BRAND}" stroke-width="6" stroke-linecap="round"/>
  </g>
</svg>"""


def _art_chat() -> str:
    """말풍선 두 개 — FAQ / 민원 빈 상태."""
    return f"""<svg {_SVG_NS} viewBox="0 0 300 140" width="300" height="140">
  {_ART_STYLE}
  <ellipse cx="150" cy="128" rx="94" ry="7" fill="{LINE}" opacity=".7"/>
  <g class="float">
    <path d="M62 34h116a12 12 0 0 1 12 12v40a12 12 0 0 1-12 12H104l-22 18v-18H62
             a12 12 0 0 1-12-12V46a12 12 0 0 1 12-12z" fill="{BRAND}"/>
    <rect x="70" y="52" width="86" height="7" rx="3.5" fill="#FFE3D0"/>
    <rect x="70" y="68" width="60" height="7" rx="3.5" fill="#FFE3D0" opacity=".8"/>
  </g>
  <g class="pop" style="transform-origin:224px 82px">
    <circle cx="224" cy="82" r="26" fill="{BRAND_SOFT}" stroke="{BRAND}" stroke-width="3"/>
    <text x="224" y="92" text-anchor="middle" font-size="27" font-weight="800"
          fill="{BRAND}">?</text>
  </g>
</svg>"""


_ART = {
    "sign_car": _art_sign_car,
    "lock": _art_lock,
    "garage": _art_garage,
    "search": _art_search,
    "chat": _art_chat,
}


def empty_state(kind: str, title: str = "", detail: str = "") -> None:
    """그림 + 한 줄 안내로 된 빈 상태 카드.

    글자만 있는 빈 화면은 '뭘 해야 하지' 싶다. 그림이 있으면 상황이 바로 읽힌다.
    kind: sign_car / lock / garage / search / chat
    """
    art = _ART.get(kind, _art_search)()
    st.html(
        f"""
        <div class="empty-state">
          {svg_img(art, 300, 140, alt=title or kind)}
          {f"<h3>{title}</h3>" if title else ""}
          {f"<p>{detail}</p>" if detail else ""}
        </div>
        """
    )


def empty_illustration() -> None:
    """홈 화면 빈 상태 그림만 (예전 이름 유지)."""
    st.html(f'<div style="text-align:center">{svg_img(_art_sign_car(), 300, 140)}</div>')


# ═══════════════════════════════════════════════════════════════
# 위험도 게이지
# ═══════════════════════════════════════════════════════════════
_GAUGE_POS = {"기록 없음": 0.14, "주의": 0.5, "위험": 0.88}
_GAUGE_COLOR = {"기록 없음": GREEN, "주의": AMBER, "위험": RED}
_CX, _CY, _R = 90.0, 84.0, 62.0


def _arc(start_deg: float, end_deg: float) -> str:
    """반원 위의 호 path. 0도가 오른쪽 끝, 180도가 왼쪽 끝."""
    sx = _CX + _R * math.cos(math.radians(start_deg))
    sy = _CY - _R * math.sin(math.radians(start_deg))
    ex = _CX + _R * math.cos(math.radians(end_deg))
    ey = _CY - _R * math.sin(math.radians(end_deg))
    return f"M {sx:.1f} {sy:.1f} A {_R} {_R} 0 0 1 {ex:.1f} {ey:.1f}"


def risk_gauge(level: str, caption: str = "") -> None:
    """단속 위험 등급을 반원 게이지로. 바늘 각도로 정도까지 보여준다."""
    pos = _GAUGE_POS.get(level, 0.5)
    color = _GAUGE_COLOR.get(level, AMBER)
    needle_deg = -88 + 176 * pos

    svg = f"""<svg {_SVG_NS} viewBox="0 0 180 108" width="180" height="108">
  <style>
    .needle {{ transform-origin: {_CX}px {_CY}px;
               animation: sweep .9s cubic-bezier(.22,1.35,.36,1) both; }}
    @keyframes sweep {{ from {{ transform: rotate(-88deg); }}
                        to   {{ transform: rotate({needle_deg:.1f}deg); }} }}
    .tip {{ animation: rise .5s .35s; }}
    @keyframes rise {{ from {{ transform: translateY(4px); }} to {{ transform: translateY(0); }} }}
    text {{ font-family: {_FONT}; }}
    @media (prefers-reduced-motion: reduce) {{
      .needle {{ animation: none; transform: rotate({needle_deg:.1f}deg); }}
      .tip {{ animation: none; }}
    }}
  </style>
  <path d="{_arc(180, 122)}" stroke="{GREEN}" stroke-width="14" fill="none"
        stroke-linecap="round" opacity=".92"/>
  <path d="{_arc(120, 60)}" stroke="{AMBER}" stroke-width="14" fill="none" opacity=".92"/>
  <path d="{_arc(58, 0)}" stroke="{RED}" stroke-width="14" fill="none"
        stroke-linecap="round" opacity=".92"/>
  <g class="needle">
    <line x1="{_CX}" y1="{_CY}" x2="{_CX}" y2="{_CY - _R + 14:.0f}"
          stroke="{INK}" stroke-width="4.5" stroke-linecap="round"/>
  </g>
  <circle cx="{_CX}" cy="{_CY}" r="8" fill="{INK}"/>
  <circle cx="{_CX}" cy="{_CY}" r="3.4" fill="#fff"/>
  <text class="tip" x="{_CX}" y="104" text-anchor="middle" font-size="15"
        font-weight="800" fill="{color}">{level}</text>
</svg>"""

    caption_html = (
        f'<div style="text-align:center;font-size:.78rem;color:{MUTED}">{caption}</div>'
        if caption
        else ""
    )
    st.html(
        f'<div style="text-align:center">'
        f'{svg_img(svg, 180, 108, alt=f"단속 위험 {level}")}{caption_html}</div>'
    )


# ═══════════════════════════════════════════════════════════════
# 절약 배너 / 리포트
# ═══════════════════════════════════════════════════════════════
def savings_banner(
    fine: int,
    lot_name: str | None = None,
    lot_fee: int | None = None,
    hours: float = 2.0,
    walk_min: int | None = None,
) -> None:
    """지도 아래에 붙는 '앗찻차!' 절약 배너 (팝업이 아니라 항상 보인다)."""
    coins = "".join(
        f'<span class="save-coin" style="left:{left}%; '
        f'animation-delay:{delay}s; font-size:{size}px">{glyph}</span>'
        for left, delay, size, glyph in (
            (8, 0.0, 18, "🪙"), (24, 0.7, 15, "💸"), (46, 1.4, 19, "🪙"),
            (68, 0.35, 16, "💸"), (86, 1.05, 17, "🪙"),
        )
    )

    if lot_name and lot_fee is not None and lot_fee < fine:
        saving = fine - lot_fee
        walk = f" · 도보 {walk_min}분" if walk_min else ""
        st.html(
            f"""
            <div class="save-banner">
              {coins}
              <div class="save-row">
                <span class="save-lede">앗찻차! 여기 세우면 {fine:,}원인데,</span>
                <span class="save-amt">{saving:,}원 아껴요</span>
              </div>
              <div class="save-sub">
                <b>{lot_name}</b> {hours:g}시간 <b>{lot_fee:,}원</b>{walk}
                — 과태료 {fine:,}원 대신 주차장을 쓰면 그만큼 남습니다.
              </div>
            </div>
            """
        )
        return

    st.html(
        f"""
        <div class="save-banner">
          {coins}
          <div class="save-row">
            <span class="save-lede">앗찻차! 여기 세우면</span>
            <span class="save-amt">{fine:,}원</span>
          </div>
          <div class="save-sub">불법주정차 과태료(승용차 일반 구역)입니다.
            아래 <b>가까운 합법 주차장</b>을 확인해 보세요.</div>
        </div>
        """
    )


def safe_banner(message: str, detail: str = "") -> None:
    """단속 기록이 없는 자리에 띄우는 초록 배너."""
    st.html(
        f"""
        <div class="save-banner is-safe">
          <div class="save-row"><span class="save-lede">{message}</span></div>
          {f'<div class="save-sub">{detail}</div>' if detail else ""}
        </div>
        """
    )


def savings_report(log_count: int, saved: int) -> None:
    """주차 기록을 근거로 '과태료 대신 주차장을 쓴 덕분에 아낀 돈'을 보여준다."""
    # 체크 표시는 stroke-dasharray 로 '그려지는' 연출을 했었는데,
    # img 안의 SVG 에서 애니메이션이 시작 상태(선 길이 0)로 멈춰 아무것도 안 보이는
    # 경우가 있었다. 지금은 정적으로 그리고 크기만 살짝 튀게 한다.
    check = f"""<svg {_SVG_NS} viewBox="0 0 48 48" width="44" height="44">
  <style>
    .tick {{ transform-origin: 24px 24px; animation: pop .5s .1s cubic-bezier(.22,1.4,.36,1); }}
    @keyframes pop {{ 0% {{ transform: scale(.55); }}
                      65% {{ transform: scale(1.12); }}
                      100% {{ transform: scale(1); }} }}
    @media (prefers-reduced-motion: reduce) {{ .tick {{ animation: none; }} }}
  </style>
  <circle cx="24" cy="24" r="22" fill="#D6F5E7"/>
  <path class="tick" d="M15 25 L21.5 31.5 L34 18" stroke="{GREEN}" stroke-width="5"
        fill="none" stroke-linecap="round" stroke-linejoin="round"/>
</svg>"""
    st.html(
        f"""
        <div class="saved-report">
          {svg_img(check, 44, 44)}
          <div>
            <div class="big">지금까지 {saved:,}원 아꼈어요</div>
            <div class="cap">주차 기록 {log_count:,}건 × 과태료 40,000원 기준 —
              그때마다 앗찻차 하지 않은 결과입니다.</div>
          </div>
        </div>
        """
    )


# ═══════════════════════════════════════════════════════════════
# 주차장 카드 / 범례 / 푸터
# ═══════════════════════════════════════════════════════════════
_CAT_EDGE = {"공영": GREEN, "민영": AMBER}


def parking_cards(rows: list[dict], hours: float) -> None:
    """추천 주차장을 카드 격자로 보여준다.

    표(dataframe)는 정보 밀도는 높지만 '어디로 갈지 고르는' 화면으로는 읽기 나쁘다.
    요금을 크게 띄우고 거리·도보·주차면을 한 덩어리로 묶으면 훑고 고르기 쉬워진다.

    rows 항목 키: name, category, kind, fee, distance_km, walk_min,
                  available, capacity, hours_text, fee_known

    fee_known 이 False 면 금액을 '0원' 으로 크게 띄우지 않는다. 원본에 요금이
    안 실린 주차장은 계산상 0원이 되는데, 그걸 그대로 보여주면 무료 주차장으로
    오해하게 된다.
    """
    cards = []
    for index, row in enumerate(rows, start=1):
        edge = _CAT_EDGE.get(str(row.get("category")), BRAND)

        tags = "".join(
            f'<span class="lot-tag">{t}</span>'
            for t in (row.get("category"), row.get("kind"))
            if t
        )

        details = []
        if row.get("distance_km") is not None:
            walk = f" · 도보 {row['walk_min']}분" if row.get("walk_min") else ""
            details.append(("거리", f"{row['distance_km']:.2f} km{walk}"))
        if row.get("hours_text"):
            details.append(("운영", row["hours_text"]))

        # 주차면은 숫자와 막대를 같이 — 숫자만으로는 여유가 얼마나인지 안 잡힌다
        bar = ""
        available, capacity = row.get("available"), row.get("capacity")
        if available is not None and capacity:
            ratio = max(0.0, min(1.0, available / capacity))
            details.append(("주차면", f"{available:,} / {capacity:,}"))
            bar = f'<div class="lot-bar"><i style="width:{ratio * 100:.0f}%"></i></div>'

        rows_html = "".join(
            f'<div class="lot-row"><span>{k}</span><span>{v}</span></div>'
            for k, v in details
        )

        if row.get("fee_known", True):
            fee_html = (
                f'<div class="lot-fee">{row["fee"]:,}원'
                f"<small>{hours:g}시간</small></div>"
            )
        else:
            fee_html = '<div class="lot-fee unknown">요금 정보 없음</div>'

        cards.append(
            f"""
            <div class="lot" style="--edge:{edge}">
              <span class="lot-rank">{index}위</span>
              <div class="lot-name">{row["name"]}</div>
              <div class="lot-tags">{tags}</div>
              {fee_html}
              <div class="lot-rows">{rows_html}</div>
              {bar}
            </div>
            """
        )

    st.html(f'<div class="lot-grid">{"".join(cards)}</div>')


def map_legend(items: list[tuple[str, str, str]], show_heat: bool = False) -> None:
    """지도 범례. items 는 (색, 이름, 부연) 목록."""
    dots = "".join(
        f'<span class="legend-item">'
        f'<span style="width:11px;height:11px;border-radius:50%;background:{color};'
        f'display:inline-block"></span>{name}'
        f"{f'<small>{note}</small>' if note else ''}</span>"
        for color, name, note in items
    )
    heat = (
        '<span class="legend-item"><span class="legend-heat"></span>'
        "단속 다발구역<small>진할수록 잦음</small></span>"
        if show_heat
        else ""
    )
    st.html(f'<div class="legend">{dots}{heat}</div>')


def footer(notes: list[str]) -> None:
    """페이지 맨 아래 출처·주의 문구."""
    lines = "".join(f"<div>{n}</div>" for n in notes)
    st.html(f'<div class="foot"><b>앗찻차!</b> · 종로구 주정차 안내{lines}</div>')


# ═══════════════════════════════════════════════════════════════
# 기타 (팀원 페이지 호환)
# ═══════════════════════════════════════════════════════════════
def feature_card(emoji: str, title: str, desc: str, owner: str) -> str:
    """홈 화면 기능 소개 카드 HTML 반환 (st.html 로 렌더)."""
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
