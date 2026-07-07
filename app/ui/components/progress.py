"""단계별 진행 표시 컴포넌트 — Presentation Layer
시각적 파이프라인 진행 표시(상단) + 타임스탬프 액티비티 로그(하단)를 제공한다.
"""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime
from typing import Generator
import streamlit as st

PIPELINE_STAGES = [
    ("📂", "데이터 로드"),
    ("🧠", "분석 계획"),
    ("💻", "코드 생성"),
    ("🛡️", "코드 검증"),
    ("⚙️", "모델 학습"),
    ("🩺", "결과 진단"),
]

_STAGE_TRIGGERS: dict[str, int] = {
    "📂": 0,
    "📋": 1,
    "💻": 2,
    "🔍": 3,
    "🚀": 4,
    "🩺": 5,
}


def _detect_stage(msg: str) -> int | None:
    for prefix, idx in _STAGE_TRIGGERS.items():
        if msg.startswith(prefix):
            return idx
    return None


def _pipeline_html(current: int, done: bool = False) -> str:
    parts = []
    for i, (icon, label) in enumerate(PIPELINE_STAGES):
        if done or i < current:
            bg = "linear-gradient(135deg,#10b981,#22d3ee)"
            fg, border, glow = "white", "rgba(16,185,129,0.6)", "0 0 12px rgba(16,185,129,0.45)"
            badge = "✓"
        elif i == current:
            bg = "linear-gradient(135deg,#6366f1,#4f46e5)"
            fg, border, glow = "white", "rgba(99,102,241,0.7)", "0 0 16px rgba(99,102,241,0.7)"
            badge = "●"
        else:
            bg = "rgba(30,41,59,0.6)"
            fg, border, glow = "#64748b", "rgba(148,163,184,0.18)", "none"
            badge = str(i + 1)

        chip = (
            f"<span style='display:inline-flex;align-items:center;gap:4px;"
            f"padding:6px 13px;border-radius:999px;font-size:12px;font-weight:700;"
            f"background:{bg};color:{fg};border:1px solid {border};"
            f"box-shadow:{glow};white-space:nowrap'>"
            f"{badge} {icon} {label}</span>"
        )
        arrow = (
            "<span style='color:#475569;font-size:16px;margin:0 1px'>›</span>"
            if i < len(PIPELINE_STAGES) - 1
            else ""
        )
        parts.append(chip + arrow)

    return (
        "<div style='display:flex;flex-wrap:wrap;align-items:center;gap:6px;"
        "padding:14px 16px;background:rgba(15,23,42,0.5);border-radius:14px;"
        "border:1px solid rgba(99,102,241,0.18);margin-bottom:10px'>"
        + "".join(parts)
        + "</div>"
    )


def _log_html(entries: list[tuple[str, str]]) -> str:
    if not entries:
        return ""
    rows = []
    for ts, msg in entries[-40:]:
        is_sub = msg.startswith("  └")
        indent = "padding-left:22px" if is_sub else ""
        color = "#64748b" if is_sub else "#e2e8f0"
        weight = "400" if is_sub else "500"
        rows.append(
            f"<div style='display:flex;gap:10px;padding:2px 0;{indent}'>"
            f"<span style='color:#475569;font-size:11px;flex-shrink:0;min-width:60px'>{ts}</span>"
            f"<span style='font-size:13px;color:{color};font-weight:{weight}'>{msg}</span>"
            f"</div>"
        )
    return (
        "<div style='font-family:\"Courier New\",monospace;"
        "background:#0f172a;padding:12px 14px;border-radius:8px;"
        "max-height:260px;overflow-y:auto;line-height:1.65'>"
        + "".join(rows)
        + "</div>"
    )


@contextmanager
def progress_status(label: str = "🤖 AI 분석 진행 중...") -> Generator[..., None, None]:
    outer = st.status(label, expanded=True)
    with outer:
        pipeline_ph = st.empty()
        log_ph = st.empty()

    current_stage: list[int] = [-1]
    entries: list[tuple[str, str]] = []

    def _refresh(done: bool = False) -> None:
        pipeline_ph.markdown(_pipeline_html(current_stage[0], done), unsafe_allow_html=True)
        log_ph.markdown(_log_html(entries), unsafe_allow_html=True)

    _refresh()

    def notify(msg: str) -> None:
        stage = _detect_stage(msg)
        if stage is not None:
            current_stage[0] = stage
        entries.append((datetime.now().strftime("%H:%M:%S"), msg))
        _refresh()

    try:
        yield notify
    except Exception as e:
        entries.append((datetime.now().strftime("%H:%M:%S"), f"❌ 오류: {e}"))
        _refresh()
        outer.update(label="❌ 분석 실패", state="error")
        raise
    else:
        _refresh(done=True)
        outer.update(label="✅ 분석 완료!", state="complete")
