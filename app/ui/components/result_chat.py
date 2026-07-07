"""분석 결과 챗봇 UI 컴포넌트 — Presentation Layer"""
from __future__ import annotations
import streamlit as st
from app.domain.models import AnalysisResult


def show_chat(result: AnalysisResult, orchestrator) -> None:
    st.divider()
    st.subheader("💬 분석 결과에 대해 질문하기")
    st.caption("모델 성능, 선택 이유, 개선 방법 등 무엇이든 물어보세요.")

    history_key = f"chat_history_{result.id}"
    if history_key not in st.session_state:
        st.session_state[history_key] = []

    history: list[dict] = st.session_state[history_key]

    for msg in history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("질문을 입력하세요..."):
        history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("답변 생성 중..."):
                response, cost = orchestrator.chat_about_result(result, history)
            st.markdown(response)
            if cost and cost.get("usd"):
                st.caption(
                    f"💰 이 답변 비용: ${cost['usd']:.4f} · "
                    f"입력 {cost['input_tokens']:,} / 출력 {cost['output_tokens']:,} 토큰"
                )

        history.append({"role": "assistant", "content": response})
        st.session_state[history_key] = history
