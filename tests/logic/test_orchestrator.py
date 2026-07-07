"""T-010 / T-011 검증 — Orchestrator Mode A / B 통합 단위 테스트"""
import json
import os
import tempfile
import pytest
import pandas as pd
from app.agents.orchestrator import Orchestrator
from app.agents.plan_agent import PlanAgent
from app.agents.code_agent import CodeAgent
from app.domain.models import ColumnSpec, ModeARequest, ModeBRequest
from app.providers.base import LLMProvider
from app.storage.session_store import InMemorySessionStore
from app.domain.models import SessionStatus

SAMPLE_CSV_DATA = "age,income,label\n25,50000,0\n30,60000,1\n35,70000,1\n40,80000,0\n22,45000,0\n28,55000,1\n"

PLAN_A_RESPONSE = json.dumps({
    "title": "LR", "description": "desc", "algorithm_family": "logistic_regression",
    "feature_strategy": "scale", "target_column": "label",
})
PLAN_B_RESPONSE = json.dumps([
    {"index": 1, "title": "LR", "description": "d", "algorithm_family": "logistic_regression", "feature_strategy": "s", "target_column": "label"},
    {"index": 2, "title": "RF", "description": "d", "algorithm_family": "random_forest", "feature_strategy": "n", "target_column": "label"},
    {"index": 3, "title": "XGB", "description": "d", "algorithm_family": "gradient_boosting", "feature_strategy": "n", "target_column": "label"},
])
GOOD_CODE = """
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
import pandas as pd
from sklearn.preprocessing import LabelEncoder

df2 = df.dropna()
X = df2[['age', 'income']]
y = df2['label']
if len(X) < 2:
    result = {'accuracy': 0.0, 'n_train': 0, 'n_test': 0, 'algorithm': 'LR'}
    model = None
else:
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42)
    model = LogisticRegression()
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    result = {'accuracy': float(accuracy_score(y_test, y_pred)), 'n_train': len(X_train), 'n_test': len(X_test), 'algorithm': 'LR'}
"""


class MockLLMProvider(LLMProvider):
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)

    def chat(self, messages, temperature=0.2) -> str:
        return self._responses.pop(0) if self._responses else "{}"

    def get_model_name(self) -> str:
        return "mock"


@pytest.fixture()
def csv_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write(SAMPLE_CSV_DATA)
        path = f.name
    yield path
    os.unlink(path)


def _build_orchestrator(llm_responses: list[str]) -> tuple[Orchestrator, InMemorySessionStore]:
    provider = MockLLMProvider(llm_responses)
    store = InMemorySessionStore()
    orch = Orchestrator(
        plan_agent=PlanAgent(llm_provider=provider),
        code_agent=CodeAgent(llm_provider=provider),
        session_store=store,
    )
    return orch, store


# ─────────── Mode A ───────────

def test_mode_a_returns_completed(csv_file):
    orch, store = _build_orchestrator([PLAN_A_RESPONSE, GOOD_CODE])
    result = orch.run_mode_a(ModeARequest(csv_path=csv_file, objective_text="label 분류해줘"))
    assert result.status == "completed"
    assert result.result is not None


def test_mode_a_status_transition(csv_file):
    orch, store = _build_orchestrator([PLAN_A_RESPONSE, GOOD_CODE])
    r = orch.run_mode_a(ModeARequest(csv_path=csv_file, objective_text="label 분류해줘"))
    session = store.get(r.session_id)
    assert session.status == SessionStatus.COMPLETED


def test_mode_a_blocked_import_returns_failed(csv_file):
    bad_code = "import requests\nresult = {}\nmodel = None"
    orch, _ = _build_orchestrator([PLAN_A_RESPONSE, bad_code])
    r = orch.run_mode_a(ModeARequest(csv_path=csv_file, objective_text="label 분류해줘"))
    assert r.status == "failed"
    assert "requests" in (r.error_message or "")


# ─────────── Mode B ───────────

def test_mode_b_propose_returns_awaiting_selection(csv_file):
    orch, _ = _build_orchestrator([PLAN_B_RESPONSE])
    r = orch.propose_plans(ModeBRequest(
        csv_path=csv_file,
        schema_columns=[ColumnSpec("age"), ColumnSpec("income"), ColumnSpec("label")],
    ))
    assert r.status == "awaiting_selection"
    assert len(r.plans) == 3


def test_mode_b_execute_selected_returns_completed(csv_file):
    orch, _ = _build_orchestrator([PLAN_B_RESPONSE, GOOD_CODE])
    propose_r = orch.propose_plans(ModeBRequest(
        csv_path=csv_file,
        schema_columns=[ColumnSpec("age"), ColumnSpec("income"), ColumnSpec("label")],
    ))
    plan_id = propose_r.plans[0].id
    exec_r = orch.execute_selected_plan(propose_r.session_id, plan_id)
    assert exec_r.status == "completed"


# ─────────── 통합 개선 루프 ───────────

class StubEval:
    """verdict를 제어하는 EvalAgent 스텁 (LLM 미사용)."""
    def __init__(self, verdicts: list[str]) -> None:
        self.verdicts = verdicts
        self.calls = 0

    def evaluate(self, result) -> dict:
        v = self.verdicts[min(self.calls, len(self.verdicts) - 1)]
        self.calls += 1
        return {"verdict": v, "checks": [], "recommendations": [], "summary": ""}


def _build_with_eval(llm_responses, stub_eval):
    provider = MockLLMProvider(llm_responses)
    store = InMemorySessionStore()
    orch = Orchestrator(
        plan_agent=PlanAgent(llm_provider=provider),
        code_agent=CodeAgent(llm_provider=provider),
        session_store=store,
        eval_agent=stub_eval,
    )
    return orch, store


def test_improvement_loop_stops_when_trustworthy(csv_file):
    stub = StubEval(["신뢰 가능"])
    orch, _ = _build_with_eval([PLAN_A_RESPONSE, GOOD_CODE], stub)
    r = orch.run_mode_a(ModeARequest(csv_path=csv_file, objective_text="x"))
    assert r.status == "completed"
    assert stub.calls == 1  # '신뢰 가능' → 첫 라운드에서 종료


def test_improvement_loop_repeats_until_max(csv_file):
    stub = StubEval(["주의 필요"])  # 계속 개선 필요 → 최대 횟수까지 반복
    orch, _ = _build_with_eval(
        [PLAN_A_RESPONSE] + [GOOD_CODE] * Orchestrator.MAX_IMPROVE_ROUNDS, stub
    )
    r = orch.run_mode_a(ModeARequest(csv_path=csv_file, objective_text="x"))
    assert r.status == "completed"
    assert stub.calls == Orchestrator.MAX_IMPROVE_ROUNDS


# ─────────── 비용 알림 — 캐시 히트 메시지 (재현성) ───────────

class _ZeroUsageProvider(LLMProvider):
    """usage_snapshot이 항상 동일값을 반환 — '실제 호출은 됐는데 토큰 증가가 없다'는
    캐시 히트 상황을 흉내낸다."""
    def chat(self, messages, temperature=0.2) -> str:
        return "{}"

    def get_model_name(self) -> str:
        return "mock"


def test_notify_cost_reports_cache_hit_on_zero_delta():
    provider = _ZeroUsageProvider()
    orch = Orchestrator(
        plan_agent=PlanAgent(llm_provider=provider),
        code_agent=CodeAgent(llm_provider=provider),
        session_store=InMemorySessionStore(),
        llm_provider=provider,
    )
    messages: list[str] = []
    before = orch._snapshot()
    orch._notify_cost(messages.append, before, "테스트 단계")
    assert any("캐시" in m for m in messages)


def test_mode_b_selected_plan_is_marked(csv_file):
    orch, store = _build_orchestrator([PLAN_B_RESPONSE, GOOD_CODE])
    propose_r = orch.propose_plans(ModeBRequest(
        csv_path=csv_file,
        schema_columns=[ColumnSpec("age"), ColumnSpec("income"), ColumnSpec("label")],
    ))
    plan_id = propose_r.plans[1].id
    orch.execute_selected_plan(propose_r.session_id, plan_id)
    session = store.get(propose_r.session_id)
    selected = [p for p in session.plans if p.is_selected]
    not_selected = [p for p in session.plans if not p.is_selected]
    assert len(selected) == 1
    assert selected[0].id == plan_id
    assert len(not_selected) == 2
