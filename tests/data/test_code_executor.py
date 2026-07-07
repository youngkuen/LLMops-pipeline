"""T-005 검증 — CodeExecutor 통합 테스트"""
import pandas as pd
import pytest
from app.executor.code_executor import run_code

SAMPLE_DF = pd.DataFrame({
    "age": [25, 30, 35, 40, 22, 28],
    "income": [50000, 60000, 70000, 80000, 45000, 55000],
    "label": [0, 1, 1, 1, 0, 0],
})

GOOD_CODE = """
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

X = df[['age', 'income']]
y = df['label']
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42)

model = LogisticRegression()
model.fit(X_train, y_train)
y_pred = model.predict(X_test)

result = {
    'accuracy': float(accuracy_score(y_test, y_pred)),
    'n_train': len(X_train),
    'n_test': len(X_test),
    'algorithm': 'LogisticRegression',
}
"""

NO_RESULT_CODE = """
from sklearn.linear_model import LogisticRegression
model = LogisticRegression()
"""

SYNTAX_ERROR_CODE = """
def broken(:
    pass
result = {}
"""

RUNTIME_ERROR_CODE = """
result = df['nonexistent_column'].sum()
model = None
"""


def test_successful_execution_returns_result_and_model():
    exec_result = run_code(GOOD_CODE, SAMPLE_DF)
    assert exec_result.success
    assert exec_result.result is not None
    assert "accuracy" in exec_result.result
    assert exec_result.model is not None


def test_missing_result_variable_returns_failure():
    exec_result = run_code(NO_RESULT_CODE, SAMPLE_DF)
    assert not exec_result.success
    assert "result" in exec_result.error_message


def test_syntax_error_returns_failure():
    exec_result = run_code(SYNTAX_ERROR_CODE, SAMPLE_DF)
    assert not exec_result.success


def test_runtime_error_returns_failure():
    exec_result = run_code(RUNTIME_ERROR_CODE, SAMPLE_DF)
    assert not exec_result.success


def test_df_is_available_in_namespace():
    code = "result = {'row_count': len(df)}\nmodel = None"
    exec_result = run_code(code, SAMPLE_DF)
    assert exec_result.success
    assert exec_result.result["row_count"] == len(SAMPLE_DF)
