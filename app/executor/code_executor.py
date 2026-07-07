"""Python 코드 실행기 — Data Layer
exec() + 공유 딕셔너리로 result/model 변수 추출.
POC 전용: 보안 격리 없음. 신뢰 환경에서만 사용.
"""
from __future__ import annotations
import io
import sys
import traceback
import pandas as pd
import numpy as np
from app.domain.models import ExecutionResult


def run_code(source_code: str, df: pd.DataFrame) -> ExecutionResult:
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()

    global_ns: dict = {
        "__builtins__": __builtins__,
        "df": df,
        "pd": pd,
        "np": np,
    }

    old_stdout, old_stderr = sys.stdout, sys.stderr
    sys.stdout = stdout_capture
    sys.stderr = stderr_capture
    try:
        exec(source_code, global_ns)  # noqa: S102
    except Exception:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        err = traceback.format_exc()
        return ExecutionResult(
            success=False,
            stderr=err,
            error_message=f"코드 실행 오류: {err.splitlines()[-1]}",
        )
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    result = global_ns.get("result")
    model = global_ns.get("model")

    if result is None:
        return ExecutionResult(
            success=False,
            stdout=stdout_capture.getvalue(),
            error_message="생성된 코드에 'result' 변수가 없습니다.",
        )
    if not isinstance(result, dict):
        return ExecutionResult(
            success=False,
            stdout=stdout_capture.getvalue(),
            error_message=f"'result' 변수가 dict가 아닙니다 (타입: {type(result).__name__})",
        )

    feature_importance = global_ns.get("feature_importance")
    if feature_importance is not None and isinstance(feature_importance, dict):
        result["feature_importance"] = feature_importance

    return ExecutionResult(
        success=True,
        result=result,
        model=model,
        stdout=stdout_capture.getvalue(),
        stderr=stderr_capture.getvalue(),
    )
