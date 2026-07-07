"""Plan Agent — Logic Layer
LLMProvider를 호출하여 AnalysisPlan을 생성한다.
Mode A: 1개, Mode B: 정확히 3개 (재시도 포함)
"""
from __future__ import annotations
import json
import re
import uuid
from app.domain.models import AnalysisPlan, DataSchema
from app.providers.base import LLMProvider
from app.loaders.csv_loader import schema_to_text

_ALGO_CLASSIFICATION = "logistic_regression|random_forest|gradient_boosting|svm|knn|decision_tree|naive_bayes"
_ALGO_REGRESSION = "linear_regression|ridge|lasso|random_forest|gradient_boosting|svr|elasticnet|decision_tree"
# 시계열: 과거값(lag) 피처 기반 tree 회귀 모델 위주
_ALGO_TIMESERIES = "random_forest|gradient_boosting|decision_tree|ridge|lasso"

_TASK_KR = {
    "classification": "분류 (Classification)",
    "regression": "회귀 (Regression)",
    "timeseries": "시계열 예측 (Time Series Forecasting)",
}


def _algos_for(task_type: str) -> str:
    if task_type == "classification":
        return _ALGO_CLASSIFICATION
    if task_type == "timeseries":
        return _ALGO_TIMESERIES
    return _ALGO_REGRESSION


def _timeseries_hint(task_type: str, time_column: str | None) -> str:
    if task_type != "timeseries":
        return ""
    col = f"'{time_column}'" if time_column else "시간 컬럼"
    return (
        f"\n이것은 시계열 예측입니다. {col} 기준으로 시간순 정렬 후, "
        "과거값(lag)·이동통계(rolling)·달력 파생변수(연/월/요일)를 피처로 만들어 "
        "회귀로 접근하세요. tree 기반 회귀 모델을 권장하며, 학습/평가는 반드시 시간순으로 분할합니다."
    )


_DECISION_GUIDE = """알고리즘 선택 원칙 (기본값이 아니라 데이터에 근거해 고를 것):
- 데이터가 작거나 해석 가능성이 중요하면 → 해석 가능한 모델 (logistic_regression / linear_regression / ridge / lasso / decision_tree)
- 데이터가 크거나 복잡하고 정확도가 우선이면 → 앙상블 모델 (random_forest / gradient_boosting)
- feature_strategy는 스키마의 실제 컬럼명을 근거로, 구체적 전처리를 명시할 것:
  범주형 인코딩, 스케일링, 결측치 처리, 그리고 이 데이터에 의미 있는 파생변수.
- description은 '왜 이 알고리즘이 이 데이터·목표에 적합한지'를 간단히 근거와 함께 설명할 것.
- 일반론적 boilerplate 금지 — 반드시 이 데이터셋에 특화된 내용."""


def _mode_a_system(task_type: str) -> str:
    algos = _algos_for(task_type)
    task_kr = _TASK_KR.get(task_type, _TASK_KR["regression"])
    hint = _timeseries_hint(task_type, None)
    return f"""You are a senior data scientist. Given a dataset schema and a business objective, design ONE well-reasoned {task_type} plan tailored to THIS specific dataset.
Task type: {task_kr}{hint}

먼저 스키마를 읽고: 컬럼 수·타입, 목표가 암시하는 타겟 컬럼을 파악하라.
target_column은 목표가 예측하려는 스키마의 정확한 컬럼명이어야 한다.

{_DECISION_GUIDE}

title, description, feature_strategy는 한국어로 작성.
Return ONLY valid JSON (no markdown, no explanation):
{{
  "title": "짧은 계획 제목 (한국어)",
  "description": "무엇을 하는지 + 왜 이 알고리즘이 이 데이터에 적합한지 (한국어)",
  "algorithm_family": "{algos}",
  "feature_strategy": "실제 컬럼 기반 구체적 전처리 전략 (한국어)",
  "target_column": "exact column name from schema to predict"
}}"""


def _mode_b_system(task_type: str, time_column: str | None = None) -> str:
    algos = _algos_for(task_type)
    task_kr = _TASK_KR.get(task_type, _TASK_KR["regression"])
    hint = _timeseries_hint(task_type, time_column)
    return f"""You are a senior data scientist. Given a data schema with column descriptions, propose EXACTLY 3 GENUINELY DIFFERENT {task_type} analysis plans that explore different trade-offs — not minor variations.
Task type: {task_kr}{hint}

세 계획은 서로 다른 관점을 대표해야 한다:
- 계획 1 — 해석 가능한 단순 베이스라인: 빠르고 설명하기 쉬운 모델
- 계획 2 — 균형: 성능과 복잡도의 균형
- 계획 3 — 고성능: 정확도를 최대화하는 앙상블/부스팅
(위 축은 가이드이며, 시계열 등 task 특성에 맞게 조정 가능)

각 계획의 규칙:
- 3개 모두 [{algos}] 중 서로 다른 algorithm_family 사용
- target_column은 스키마의 정확한 컬럼명
- description에 '이 접근이 이 데이터에 왜 적합한지 + 어떤 트레이드오프(속도·해석성 vs 정확도)를 택하는지' 설명
- feature_strategy는 실제 컬럼명 기반 구체적 전처리

title, description, feature_strategy는 한국어로 작성.
Return ONLY valid JSON array (no markdown, no explanation):
[
  {{"index": 1, "title": "짧은 제목", "description": "설명 + 트레이드오프", "algorithm_family": "...", "feature_strategy": "구체적 전략", "target_column": "..."}},
  {{"index": 2, "title": "짧은 제목", "description": "설명 + 트레이드오프", "algorithm_family": "...", "feature_strategy": "구체적 전략", "target_column": "..."}},
  {{"index": 3, "title": "짧은 제목", "description": "설명 + 트레이드오프", "algorithm_family": "...", "feature_strategy": "구체적 전략", "target_column": "..."}}
]"""


def _parse_json(text: str):
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    return json.loads(text.strip())


class PlanAgent:
    MAX_RETRIES = 3

    def __init__(self, llm_provider: LLMProvider) -> None:
        self._llm = llm_provider

    def create_plan_mode_a(
        self, session_id: str, schema: DataSchema, objective_text: str,
        task_type: str = "classification",
    ) -> AnalysisPlan:
        schema_text = schema_to_text(schema)
        user_msg = f"Schema:\n{schema_text}\n\nObjective: {objective_text}"
        messages = [
            {"role": "system", "content": _mode_a_system(task_type)},
            {"role": "user", "content": user_msg},
        ]
        raw = self._llm.chat(messages)
        data = _parse_json(raw)
        return AnalysisPlan(
            id=str(uuid.uuid4()),
            session_id=session_id,
            index=1,
            title=data["title"],
            description=data["description"],
            algorithm_family=data["algorithm_family"],
            feature_strategy=data["feature_strategy"],
            target_column=data.get("target_column"),
            is_selected=True,
            task_type=task_type,
        )

    def propose_plans_mode_b(
        self, session_id: str, schema: DataSchema, task_type: str = "classification",
        time_column: str | None = None,
    ) -> list[AnalysisPlan]:
        schema_text = schema_to_text(schema)
        user_msg = f"Schema:\n{schema_text}"
        messages = [
            {"role": "system", "content": _mode_b_system(task_type, time_column)},
            {"role": "user", "content": user_msg},
        ]

        for attempt in range(self.MAX_RETRIES):
            raw = self._llm.chat(messages)
            try:
                data_list = _parse_json(raw)
            except (json.JSONDecodeError, ValueError):
                continue

            if not isinstance(data_list, list) or len(data_list) < 3:
                continue

            algos = {d.get("algorithm_family") for d in data_list[:3]}
            if len(algos) < 3:
                messages.append({"role": "assistant", "content": raw})
                messages.append({
                    "role": "user",
                    "content": "각 plan의 algorithm_family가 달라야 합니다. 다시 시도하세요.",
                })
                continue

            return [
                AnalysisPlan(
                    id=str(uuid.uuid4()),
                    session_id=session_id,
                    index=i + 1,
                    title=d["title"],
                    description=d["description"],
                    algorithm_family=d["algorithm_family"],
                    feature_strategy=d["feature_strategy"],
                    target_column=d.get("target_column"),
                    task_type=task_type,
                    time_column=time_column,
                )
                for i, d in enumerate(data_list[:3])
            ]

        raise RuntimeError(f"Mode B 계획 3개 생성 실패 ({self.MAX_RETRIES}회 재시도)")
