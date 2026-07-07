"""다크 모던 SaaS 디자인 테마 — Presentation Layer
전역 CSS 주입 및 Hero/섹션 헤더 헬퍼를 제공한다.
백엔드 로직과 무관하며, 순수하게 시각적 레이어만 담당한다.
"""
from __future__ import annotations
import streamlit as st

# 디자인 토큰 (다크 모던 SaaS)
#   배경      #0b1120 / #0f172a
#   카드      rgba(30,41,59,.55) + 보라 테두리
#   액센트    #6366f1 (인디고) · #22d3ee (시안)
#   텍스트    #e2e8f0 / 보조 #94a3b8

_GLOBAL_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

:root {
    --bg-0: #0b1120;
    --bg-1: #0f172a;
    --card: rgba(30, 41, 59, 0.55);
    --card-border: rgba(99, 102, 241, 0.22);
    --accent: #6366f1;
    --accent-2: #22d3ee;
    --text: #e2e8f0;
    --muted: #94a3b8;
}

html, body, [class*="css"], .stApp, [data-testid="stAppViewContainer"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

/* 앱 배경 — 은은한 방사형 글로우 */
.stApp {
    background:
        radial-gradient(1200px 600px at 12% -8%, rgba(99,102,241,0.16), transparent 60%),
        radial-gradient(1000px 520px at 92% 4%, rgba(34,211,238,0.10), transparent 55%),
        var(--bg-0);
}

/* 콘텐츠 폭 / 여백 */
.block-container {
    max-width: 1180px;
    padding-top: 2.2rem;
    padding-bottom: 4rem;
}

/* 헤더 바 투명 처리 */
[data-testid="stHeader"] { background: transparent; }

h1, h2, h3, h4 { letter-spacing: -0.02em; font-weight: 700; }

/* ── 글래스 메트릭 카드 ───────────────────────────────── */
[data-testid="stMetric"] {
    background: var(--card);
    border: 1px solid var(--card-border);
    border-radius: 16px;
    padding: 18px 20px;
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    box-shadow: 0 8px 28px rgba(2, 6, 23, 0.45),
                inset 0 1px 0 rgba(255, 255, 255, 0.04);
    transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease;
}
[data-testid="stMetric"]:hover {
    transform: translateY(-3px);
    border-color: rgba(99, 102, 241, 0.55);
    box-shadow: 0 14px 36px rgba(79, 70, 229, 0.28);
}
[data-testid="stMetricLabel"] p {
    color: var(--muted) !important;
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}
[data-testid="stMetricValue"] {
    font-weight: 800 !important;
    background: linear-gradient(90deg, #c7d2fe, #67e8f9);
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
}

/* ── 버튼 — 그라데이션 + 글로우 ───────────────────────── */
.stButton > button, .stDownloadButton > button {
    background: linear-gradient(135deg, #6366f1 0%, #4f46e5 60%, #22d3ee 160%);
    color: #ffffff;
    border: none;
    border-radius: 12px;
    padding: 0.55rem 1.4rem;
    font-weight: 700;
    letter-spacing: 0.01em;
    box-shadow: 0 6px 20px rgba(79, 70, 229, 0.40);
    transition: transform .15s ease, box-shadow .15s ease, filter .15s ease;
}
.stButton > button:hover, .stDownloadButton > button:hover {
    transform: translateY(-2px);
    box-shadow: 0 10px 28px rgba(79, 70, 229, 0.55);
    filter: brightness(1.06);
}
.stButton > button:disabled {
    background: #1e293b;
    color: #475569;
    box-shadow: none;
}

/* ── 탭 — pill 스타일 ─────────────────────────────────── */
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    gap: 6px;
    background: rgba(15, 23, 42, 0.5);
    padding: 6px;
    border-radius: 14px;
    border: 1px solid rgba(148, 163, 184, 0.12);
}
[data-testid="stTabs"] [data-baseweb="tab"] {
    height: auto;
    padding: 8px 16px;
    border-radius: 10px;
    color: var(--muted);
    font-weight: 600;
    background: transparent;
}
[data-testid="stTabs"] [aria-selected="true"] {
    background: linear-gradient(135deg, rgba(99,102,241,0.9), rgba(79,70,229,0.9));
    color: #ffffff !important;
    box-shadow: 0 4px 14px rgba(79, 70, 229, 0.4);
}
[data-testid="stTabs"] [data-baseweb="tab-highlight"],
[data-testid="stTabs"] [data-baseweb="tab-border"] { display: none; }

/* ── 입력 위젯 ────────────────────────────────────────── */
.stTextInput input, .stTextArea textarea, .stNumberInput input,
[data-baseweb="select"] > div {
    background: rgba(15, 23, 42, 0.6) !important;
    border: 1px solid rgba(148, 163, 184, 0.18) !important;
    border-radius: 10px !important;
    color: var(--text) !important;
}
.stTextInput input:focus, .stTextArea textarea:focus {
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.25) !important;
}

/* 라디오 / 탭 등 위에 카드 느낌 컨테이너 */
[data-testid="stExpander"] {
    background: var(--card);
    border: 1px solid var(--card-border);
    border-radius: 14px;
}

/* DataFrame 모서리 둥글게 */
[data-testid="stDataFrame"] {
    border-radius: 12px;
    overflow: hidden;
    border: 1px solid rgba(148, 163, 184, 0.14);
}

/* 알림 박스 라운드 */
[data-testid="stAlert"] { border-radius: 12px; }

/* 채팅 입력 */
[data-testid="stChatInput"] textarea {
    background: rgba(15, 23, 42, 0.6) !important;
}

/* st.status 컨테이너 글래스화 */
[data-testid="stStatus"], [data-testid="stExpanderDetails"] {
    border-radius: 14px;
}
</style>
"""


def inject_theme() -> None:
    """전역 CSS를 주입한다. main()에서 set_page_config 직후 1회 호출."""
    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)


def render_hero(title: str, subtitle: str, badge: str = "AI MODEL PIPELINE") -> None:
    """앱 상단 Hero 헤더를 렌더링한다."""
    st.markdown(
        f"""
        <div style="
            margin: 0 0 1.4rem 0; padding: 26px 30px;
            background: linear-gradient(135deg, rgba(30,41,59,0.75), rgba(15,23,42,0.55));
            border: 1px solid rgba(99,102,241,0.28);
            border-radius: 20px;
            box-shadow: 0 16px 48px rgba(2,6,23,0.5), inset 0 1px 0 rgba(255,255,255,0.05);
            backdrop-filter: blur(12px);">
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;">
                <span style="width:11px;height:11px;border-radius:50%;
                    background:linear-gradient(135deg,#6366f1,#22d3ee);
                    box-shadow:0 0 14px rgba(99,102,241,0.9);"></span>
                <span style="font-size:11px;font-weight:800;letter-spacing:0.18em;
                    color:#818cf8;">{badge}</span>
            </div>
            <div style="font-size:2rem;font-weight:800;letter-spacing:-0.03em;
                background:linear-gradient(90deg,#f1f5f9,#a5b4fc 55%,#67e8f9);
                -webkit-background-clip:text;background-clip:text;
                -webkit-text-fill-color:transparent;line-height:1.15;">{title}</div>
            <div style="margin-top:8px;color:#94a3b8;font-size:0.98rem;">{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_header(icon: str, title: str, subtitle: str = "") -> None:
    """페이지/섹션 헤더를 일관된 스타일로 렌더링한다."""
    sub = (
        f"<div style='color:#94a3b8;font-size:0.92rem;margin-top:2px;'>{subtitle}</div>"
        if subtitle else ""
    )
    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:12px;margin:0.2rem 0 1rem 0;">
            <div style="width:42px;height:42px;border-radius:12px;flex-shrink:0;
                display:flex;align-items:center;justify-content:center;font-size:20px;
                background:linear-gradient(135deg,rgba(99,102,241,0.25),rgba(34,211,238,0.18));
                border:1px solid rgba(99,102,241,0.35);">{icon}</div>
            <div>
                <div style="font-size:1.32rem;font-weight:700;letter-spacing:-0.02em;
                    color:#f1f5f9;">{title}</div>
                {sub}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
