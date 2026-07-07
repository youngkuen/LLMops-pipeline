"""Spec Agent — Logic Layer
데이터의 컬럼 목록과 사용자가 올린 명세서 텍스트를 받아,
각 컬럼의 설명·타겟 여부와 분석 유형을 LLM으로 추출한다.
사용자가 컬럼마다 직접 타이핑하는 수고를 대신한다.
"""
from __future__ import annotations
import json
import re
from app.providers.base import LLMProvider

_SYSTEM = """당신은 데이터 명세서에서 컬럼 정보를 추출하는 도우미입니다.
주어진 '데이터 컬럼 목록'과 '명세서 텍스트'를 대조하여, 각 컬럼의 설명과 예측 타겟 여부, 전체 분석 유형을 판단하세요.

규칙:
- 컬럼명은 반드시 주어진 '데이터 컬럼 목록'에 있는 이름을 그대로 사용하세요 (명세서의 표현이 달라도 매칭).
- 명세서에서 설명을 찾을 수 없는 컬럼은 description을 빈 문자열로 두세요.
- is_target은 예측 대상(목표 변수) 컬럼 하나에만 true. 명세서에 명시가 없으면 가장 그럴듯한 결과 변수 하나를 고르세요.
- task_type은 타겟이 범주형이면 "classification", 연속 수치면 "regression", 시간 흐름에 따른 미래 예측이면 "timeseries".

반드시 아래 JSON 형식으로만 응답하세요 (마크다운·설명 없이):
{
  "task_type": "classification",
  "columns": [
    {"name": "정확한_컬럼명", "description": "한국어 설명", "is_target": false}
  ]
}"""


class SpecAgent:
    def __init__(self, llm_provider: LLMProvider) -> None:
        self._llm = llm_provider

    def extract(self, column_names: list[str], spec_text: str) -> dict:
        """반환: {"task_type": str|None, "columns": {name: {"description": str, "is_target": bool}}}
        실패 시 빈 결과를 반환한다 (UI는 수동 입력으로 폴백)."""
        user_msg = (
            f"데이터 컬럼 목록: {column_names}\n\n"
            f"명세서 텍스트:\n{spec_text}"
        )
        try:
            raw = self._llm.chat(
                [{"role": "system", "content": _SYSTEM},
                 {"role": "user", "content": user_msg}],
                temperature=0.1,
            )
            raw = re.sub(r"```(?:json)?\s*", "", raw).replace("```", "").strip()
            data = json.loads(raw)
        except Exception:
            return {"task_type": None, "columns": {}}

        valid = set(column_names)
        columns: dict[str, dict] = {}
        for item in data.get("columns", []):
            name = item.get("name")
            if name in valid:
                columns[name] = {
                    "description": str(item.get("description", "")).strip(),
                    "is_target": bool(item.get("is_target", False)),
                }

        task_type = data.get("task_type")
        if task_type not in ("classification", "regression", "timeseries"):
            task_type = None

        return {"task_type": task_type, "columns": columns}
