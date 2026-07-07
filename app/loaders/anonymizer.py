"""개인정보(PII) 탐지 및 마스킹 — Data Layer
컬럼명 패턴 + 실제 값 패턴(정규식)으로 민감 정보를 탐지하고, LLM에 전달되기 전에 마스킹한다.
새 라이브러리 없이 표준 re 모듈만 사용한다.
"""
from __future__ import annotations
import re
import pandas as pd

PII_LABELS_KR = {
    "name": "이름",
    "email": "이메일",
    "phone": "전화번호",
    "resident_id": "주민번호",
    "address": "주소",
    "card": "카드/계좌",
}

# 컬럼명으로 판별 (값 패턴이 없는 종류: 이름, 주소는 값만 봐서는 알기 어려움)
_COLUMN_NAME_PATTERNS: dict[str, re.Pattern] = {
    "name": re.compile(r"(name|이름|성명)", re.IGNORECASE),
    "email": re.compile(r"(email|이메일|메일)", re.IGNORECASE),
    "phone": re.compile(r"(phone|tel|전화|연락처|휴대폰)", re.IGNORECASE),
    "resident_id": re.compile(r"(ssn|주민번호|주민등록)", re.IGNORECASE),
    "address": re.compile(r"(address|addr|주소)", re.IGNORECASE),
    "card": re.compile(r"(card|카드|계좌|account)", re.IGNORECASE),
}

# 셀 값 전체가 이 패턴에 맞으면 해당 종류로 판별 (컬럼명이 애매해도 값으로 탐지)
_VALUE_PATTERNS: dict[str, re.Pattern] = {
    "email": re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"),
    "phone": re.compile(r"^0\d{1,2}[-.\s]?\d{3,4}[-.\s]?\d{4}$"),
    "resident_id": re.compile(r"^\d{6}[-\s]?[1-4]\d{6}$"),
    "card": re.compile(r"^\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}$"),
}

# 자유 텍스트(명세서 등)에서 문장 중간에 섞인 값을 찾을 때 쓰는 비고정 패턴
_LOOSE_VALUE_PATTERNS: dict[str, re.Pattern] = {
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "phone": re.compile(r"0\d{1,2}[-.\s]?\d{3,4}[-.\s]?\d{4}"),
    "resident_id": re.compile(r"\d{6}[-\s]?[1-4]\d{6}"),
    "card": re.compile(r"\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}"),
}

_VALUE_SAMPLE_SIZE = 50
_VALUE_MATCH_RATIO = 0.5  # 샘플 중 이 비율 이상 패턴에 맞으면 해당 컬럼을 PII로 판정


def detect_pii_columns(df: pd.DataFrame, column_names: list[str]) -> dict[str, str]:
    """컬럼명과 실제 값을 함께 검사해 {컬럼명: PII종류}를 반환한다.
    컬럼명 매칭을 우선 적용하고(이름/주소는 값 패턴이 없어 컬럼명으로만 판별 가능),
    컬럼명으로 못 잡으면 실제 셀 값 샘플을 정규식으로 스캔한다."""
    result: dict[str, str] = {}
    for col in column_names:
        for kind, pattern in _COLUMN_NAME_PATTERNS.items():
            if pattern.search(col):
                result[col] = kind
                break
        if col in result or col not in df.columns:
            continue

        series = df[col].dropna().astype(str).head(_VALUE_SAMPLE_SIZE)
        if series.empty:
            continue
        for kind, pattern in _VALUE_PATTERNS.items():
            match_ratio = series.str.match(pattern).mean()
            if match_ratio >= _VALUE_MATCH_RATIO:
                result[col] = kind
                break
    return result


def mask_value(value: str, kind: str) -> str:
    """탐지된 종류에 맞춰 값의 일부만 보이게 마스킹한다."""
    value = str(value)
    if kind == "email":
        local, sep, domain = value.partition("@")
        return f"{local[:1]}***@{domain}" if sep else "***"
    if kind == "phone":
        digits = re.sub(r"\D", "", value)
        return f"{digits[:3]}-****-{digits[-4:]}" if len(digits) >= 7 else "***"
    if kind == "resident_id":
        digits = re.sub(r"[-\s]", "", value)
        return f"{digits[:6]}-*******" if len(digits) >= 6 else "***"
    if kind == "card":
        digits = re.sub(r"\D", "", value)
        return f"****-****-****-{digits[-4:]}" if len(digits) >= 4 else "***"
    if kind == "name":
        return f"{value[0]}{'*' * max(len(value) - 1, 1)}" if value else "***"
    return "***"


def mask_text(text: str) -> str:
    """자유 텍스트(업로드된 명세서 등)에서 이메일·전화번호·주민번호·카드번호 패턴을
    찾아 마스킹한다. LLM에 텍스트를 넘기기 전 안전장치로 사용한다."""
    for kind, pattern in _LOOSE_VALUE_PATTERNS.items():
        text = pattern.sub(lambda m, k=kind: mask_value(m.group(0), k), text)
    return text
