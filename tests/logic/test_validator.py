"""T-007 검증 — Validator 화이트리스트 테스트"""
import pytest
from app.agents.validator import validate_code


VALID_CODE = """
import pandas as pd
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split

X = df[['a', 'b']]
y = df['target']
model = LogisticRegression()
model.fit(X, y)
result = {'accuracy': 0.9}
"""

BLOCKED_REQUESTS = """
import requests
result = {}
"""

BLOCKED_OS = """
import os
os.system('rm -rf /')
result = {}
"""

BLOCKED_SUBPROCESS = """
import subprocess
result = {}
"""

SYNTAX_ERROR_CODE = """
def broken(:
    pass
"""

MIXED_ALLOWED_BLOCKED = """
import pandas as pd
import requests
from sklearn.linear_model import LogisticRegression
result = {}
"""


def test_valid_sklearn_code_passes():
    r = validate_code(VALID_CODE)
    assert r.is_valid


def test_requests_is_blocked():
    r = validate_code(BLOCKED_REQUESTS)
    assert not r.is_valid
    assert "requests" in r.blocked_imports


def test_os_is_blocked():
    r = validate_code(BLOCKED_OS)
    assert not r.is_valid
    assert "os" in r.blocked_imports


def test_subprocess_is_blocked():
    r = validate_code(BLOCKED_SUBPROCESS)
    assert not r.is_valid


def test_syntax_error_returns_invalid():
    r = validate_code(SYNTAX_ERROR_CODE)
    assert not r.is_valid
    assert "문법 오류" in r.error_message


def test_mixed_allowed_blocked_reports_blocked():
    r = validate_code(MIXED_ALLOWED_BLOCKED)
    assert not r.is_valid
    assert "requests" in r.blocked_imports


def test_xgboost_allowed():
    code = "import xgboost as xgb\nresult = {}"
    r = validate_code(code)
    assert r.is_valid


def test_lightgbm_allowed():
    code = "import lightgbm as lgb\nresult = {}"
    r = validate_code(code)
    assert r.is_valid
