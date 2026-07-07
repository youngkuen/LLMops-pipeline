"""Streamlit 앱 진입점 — Presentation Layer
의존성 주입: LLMProvider / CodeExecutor / SessionStore 를 조립하고 Orchestrator에 주입한다.
"""
import os
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from app.providers.anthropic_provider import AnthropicProvider
from app.providers.caching_provider import CachingLLMProvider
from app.agents.plan_agent import PlanAgent
from app.agents.code_agent import CodeAgent
from app.agents.chat_agent import ChatAgent
from app.agents.eval_agent import EvalAgent
from app.agents.spec_agent import SpecAgent
from app.agents.orchestrator import Orchestrator
from app.executor.code_executor import run_code  # noqa: F401 (sideeffect import check)
from app.storage.session_store import InMemorySessionStore
from app.ui import mode_a, mode_b  # noqa: F401 — mode_a는 현재 숨김, 복원용 보존
from app.ui.theme import inject_theme, render_hero


@st.cache_resource
def _build_orchestrator() -> Orchestrator:
    provider = AnthropicProvider(
        api_key=os.environ.get("ANTHROPIC_API_KEY"),
        model=os.environ.get("LLM_MODEL", "claude-sonnet-4-6"),
    )
    # 재현성: 동일 요청 재실행 시 캐시된 응답을 재사용 (API 비용도 절감됨)
    provider = CachingLLMProvider(provider)
    store = InMemorySessionStore()
    return Orchestrator(
        plan_agent=PlanAgent(llm_provider=provider),
        code_agent=CodeAgent(llm_provider=provider),
        chat_agent=ChatAgent(llm_provider=provider),
        eval_agent=EvalAgent(llm_provider=provider),
        spec_agent=SpecAgent(llm_provider=provider),
        session_store=store,
        llm_provider=provider,
    )


def main() -> None:
    st.set_page_config(
        page_title="AI 모델 생성 파이프라인",
        page_icon="🤖",
        layout="wide",
    )
    inject_theme()
    render_hero(
        title="AI 모델 생성 파이프라인",
        subtitle="데이터를 올리면 AI가 분석 계획부터 모델 학습·진단까지 자동으로 수행합니다.",
    )

    orchestrator = _build_orchestrator()

    # Mode A(자연어 목표)는 현재 숨김 — 코드는 mode_a.py에 보존되어 있으며 추후 복원 가능.
    # 교수 자문(2026-07): Mode B 단일 운영 + 질문지형 템플릿으로 전환.
    mode_b.render(orchestrator)


if __name__ == "__main__":
    main()
