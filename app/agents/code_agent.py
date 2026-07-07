"""Code Agent — Logic Layer
선택된 AnalysisPlan과 DataSchema를 받아 실행 가능한 Python 코드를 생성한다.
생성된 코드는 반드시 result(dict)와 model 변수를 정의해야 한다.
ML 방법론 하네스(.harness/ml/)가 적용되어 게이트 위반 시 최대 2회 재생성한다.
"""
from __future__ import annotations
import uuid
from pathlib import Path
from app.domain.models import AnalysisPlan, DataSchema, GeneratedCode
from app.providers.base import LLMProvider
from app.loaders.csv_loader import schema_to_text
from app.agents import ml_gates

_HARNESS_PROMPT_PATH = Path(__file__).parent.parent.parent / ".harness" / "ml" / "prompt-template.md"


def _load_harness_prompt() -> str:
    try:
        return _HARNESS_PROMPT_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


_HARNESS_PROMPT = _load_harness_prompt()

_RESULT_SPEC_CLASSIFICATION = """
REQUIRED VARIABLES — define ALL at the end:

result = {
    'accuracy': float,
    'f1': float,               # weighted f1 score
    'n_train': int,
    'n_test': int,
    'algorithm': str,
    'eda': {
        'shape': [int, int],
        'null_counts': {col: int},
        'class_distribution': {str(label): int},
        'numeric_stats': {col: {'mean': float, 'std': float, 'min': float, 'max': float}},
        'high_correlation_pairs': [[col_a, col_b, float(corr)], ...],  # see rule below, [] if none
    },
    'preprocessing': ['한국어로 단계별 설명'],
    'derived_features': ['파생변수명: 설명 (없으면 빈 리스트)'],
    'model_selection_reason': '이 알고리즘이 왜 적합한지 한국어로 설명',
    'hyperparameter_tuning': {
        'method': 'RandomizedSearchCV',
        'param_distributions': {param: [v1, v2]},
        'best_params': {param: value},
        'best_cv_score': float,
    },
}
model = <RandomizedSearchCV.best_estimator_>
# define only if model has feature_importances_:
feature_importance = {col_name: float(importance)}"""

_RESULT_SPEC_REGRESSION = """
REQUIRED VARIABLES — define ALL at the end:

result = {
    'rmse': float,
    'mae': float,
    'r2': float,
    'n_train': int,
    'n_test': int,
    'algorithm': str,
    'eda': {
        'shape': [int, int],
        'null_counts': {col: int},
        'target_stats': {'mean': float, 'std': float, 'min': float, 'max': float},
        'numeric_stats': {col: {'mean': float, 'std': float, 'min': float, 'max': float}},
        'high_correlation_pairs': [[col_a, col_b, float(corr)], ...],  # see rule below, [] if none
    },
    'preprocessing': ['한국어로 단계별 설명'],
    'derived_features': ['파생변수명: 설명 (없으면 빈 리스트)'],
    'model_selection_reason': '이 알고리즘이 왜 적합한지 한국어로 설명',
    'hyperparameter_tuning': {
        'method': 'RandomizedSearchCV',
        'param_distributions': {param: [v1, v2]},
        'best_params': {param: value},
        'best_cv_score': float,
    },
}
model = <RandomizedSearchCV.best_estimator_>
# define only if model has feature_importances_:
feature_importance = {col_name: float(importance)}"""

_BASE_RULES = """
AVAILABLE LIBRARIES: pandas, numpy, scipy, sklearn, xgboost, lightgbm, matplotlib, warnings, imblearn

ADDITIONAL RULES:
1. `df` (pandas DataFrame) is pre-loaded — do NOT read any file
2. Drop columns whose name starts with '__' (internal metadata)
3. For object/string dtype columns (except target):
   - unique values <= 50: LabelEncoder
   - unique values > 50: drop (free text / ID)
4. For numeric columns: pd.to_numeric(df[col], errors='coerce')
5. Drop rows with ANY NaN after encoding
6. Convert numpy scalars to Python native types: float() or int()
7. Use RandomizedSearchCV (n_iter=20, cv=3, random_state=42) instead of GridSearchCV
8. Multicollinearity check: on the encoded feature matrix (before train/test split), compute
   the pairwise Pearson correlation between numeric feature columns (exclude the target).
   List column pairs with abs(correlation) > 0.9 as high_correlation_pairs (sorted by abs(corr)
   descending, at most 10 pairs). Use [] if none exceed the threshold.
9. Reproducibility — set random_state=42 on EVERY call that accepts a random_state parameter
   (train_test_split, RandomizedSearchCV/GridSearchCV, SMOTE, and any estimator whose
   constructor supports random_state, e.g. RandomForest*, GradientBoosting*, DecisionTree*,
   ExtraTrees*, XGB*, LGBM*, SGD*, Ridge/Lasso/ElasticNet, SVC, LogisticRegression).
   Do NOT pass random_state to estimators that do not accept it (e.g. KNeighbors*,
   *NB (naive bayes), LinearRegression, SVR) — that raises a TypeError.
   Also call np.random.seed(42) once near the top of the script as a general safety net.
10. Return ONLY raw Python code — no markdown fences, no explanation"""


_TIMESERIES_RULES = """
TIME SERIES RULES (this is a forecasting task, solved as regression on lag features):
1. Parse the time column with pd.to_datetime(errors='coerce') and SORT df by it ascending FIRST
2. Create lag features of the target using .shift(): t-1, t-2, t-3, t-7
3. Create rolling features (mean/std) over windows (e.g., 3, 7). Apply .shift(1) BEFORE rolling to avoid using the current row (no leakage)
4. Add calendar features from the time column: year, month, day, dayofweek
5. Drop the raw time column from X (keep only engineered features), and drop rows with NaN introduced by lag/rolling
6. CHRONOLOGICAL split — do NOT shuffle. Use train_test_split(..., shuffle=False) OR slice the last 20-30% of rows as the test set
7. NEVER use future information to predict the past (no random shuffle anywhere in the pipeline)
8. Metrics are the same as regression: rmse, mae, r2"""


def _build_system(task_type: str) -> str:
    task_label = "classification" if task_type == "classification" else "regression"
    result_spec = _RESULT_SPEC_CLASSIFICATION if task_type == "classification" else _RESULT_SPEC_REGRESSION
    extra = f"\n\n---\n{_TIMESERIES_RULES}" if task_type == "timeseries" else ""
    return (
        f"You are a Python ML expert. Write a complete, executable Python {task_label} script.\n\n"
        f"{_HARNESS_PROMPT}\n\n"
        f"---\n{_BASE_RULES}\n\n"
        f"---\n{result_spec}"
        f"{extra}"
    )


class CodeAgent:
    def __init__(self, llm_provider: LLMProvider) -> None:
        self._llm = llm_provider

    def generate_code(
        self, plan: AnalysisPlan, schema: DataSchema, improvement_feedback: str = ""
    ) -> GeneratedCode:
        task_type = getattr(plan, "task_type", "classification")
        time_column = getattr(plan, "time_column", None)
        schema_text = schema_to_text(schema)
        system = _build_system(task_type)
        time_line = (
            f"Time column (sort & build lag features by this): {time_column}\n"
            if task_type == "timeseries" and time_column else ""
        )
        user_content = (
            f"Plan: {plan.title}\n"
            f"Description: {plan.description}\n"
            f"Algorithm: {plan.algorithm_family}\n"
            f"Feature strategy: {plan.feature_strategy}\n"
            f"Target column: {plan.target_column or 'determine from schema'}\n"
            f"{time_line}\n"
            f"Schema:\n{schema_text}"
        )
        if improvement_feedback:
            user_content += (
                "\n\n[직전 시도 결과 — 아래 문제를 개선하여 더 나은 성능의 코드를 작성하세요]\n"
                f"{improvement_feedback}"
            )

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ]

        source_code = ""
        for attempt in range(3):
            raw = self._llm.chat(messages, temperature=0.1)
            source_code = _strip_fences(raw)

            violations = ml_gates.run_all(source_code, task_type)
            if not violations:
                break

            if attempt < 2:
                violation_text = "\n".join(f"- {v}" for v in violations)
                messages.append({"role": "assistant", "content": raw})
                messages.append({
                    "role": "user",
                    "content": (
                        f"코드에 방법론적 위반이 {len(violations)}건 발견되었습니다. "
                        f"수정 후 전체 코드를 다시 작성하세요:\n{violation_text}"
                    ),
                })

        deps = _detect_deps(source_code)
        return GeneratedCode(
            id=str(uuid.uuid4()),
            plan_id=plan.id,
            source_code=source_code,
            dependencies=deps,
        )


def _strip_fences(code: str) -> str:
    """LLM 응답에서 실행 가능한 파이썬 코드만 추출한다.
    언어 태그(```python·```py 등)가 붙은 펜스, 앞뒤 설명 문장, 펜스 없는 설명 문장까지 방어한다.
    """
    import re
    text = code.strip()
    # 1) 펜스 블록이 있으면 그 안의 내용만 취한다 (언어 태그 종류 무관, 여러 개면 가장 긴 것).
    blocks = re.findall(r"```[^\n`]*\n(.*?)```", text, re.DOTALL)
    if blocks:
        text = max(blocks, key=len).strip()
    else:
        # 닫는 펜스가 없는 경우: 앞뒤에 붙은 펜스 라인만 제거한다.
        text = re.sub(r"^```[^\n`]*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text).strip()
    # 2) 그래도 첫 줄이 설명 문장이면(파싱 실패), 파싱되는 지점까지 앞 줄을 버린다.
    if text and not _is_parseable(text):
        lines = text.split("\n")
        for i in range(1, len(lines)):
            candidate = "\n".join(lines[i:]).strip()
            if candidate and _is_parseable(candidate):
                return candidate
    return text


def _is_parseable(src: str) -> bool:
    import ast
    try:
        ast.parse(src)
        return True
    except SyntaxError:
        return False


def _detect_deps(code: str) -> list[str]:
    import ast
    deps = set()
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    deps.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                deps.add(node.module.split(".")[0])
    except SyntaxError:
        pass
    return sorted(deps)
