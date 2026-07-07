"""명세서 파일 → 텍스트 추출 — Data Layer
사용자가 올린 명세서 파일(형식 자유: txt/md/csv/tsv/xlsx/xls)을 LLM이 읽을 수 있는
평문 텍스트로 변환한다. 형식별 로딩만 담당하며, 의미 해석은 Logic Layer(SpecAgent)가 한다.
"""
from __future__ import annotations
import io
import pandas as pd

_TEXT_EXT = {".txt", ".md", ".csv", ".tsv", ".text"}
_EXCEL_EXT = {".xlsx", ".xls", ".xlsm"}
_MAX_CHARS = 8000  # 프롬프트 과다 방지


def extract_spec_text(filename: str, data: bytes) -> str:
    """파일명 확장자로 형식을 판별해 텍스트를 반환한다.

    filename: 원본 파일명 (확장자 판별용)
    data: 파일 바이트
    """
    ext = _ext(filename)

    if ext in _EXCEL_EXT:
        text = _excel_to_text(data)
    else:
        # 텍스트 계열(및 미지정 확장자)은 디코딩 시도
        text = _decode_text(data)

    text = text.strip()
    if len(text) > _MAX_CHARS:
        text = text[:_MAX_CHARS] + "\n...(이하 생략)"
    return text


def _ext(filename: str) -> str:
    name = (filename or "").lower()
    dot = name.rfind(".")
    return name[dot:] if dot != -1 else ""


def _decode_text(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp949", "utf-8", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _excel_to_text(data: bytes) -> str:
    """엑셀의 모든 시트를 읽어 텍스트로 직렬화한다."""
    sheets = pd.read_excel(io.BytesIO(data), sheet_name=None, header=None)
    parts = []
    for sheet_name, df in sheets.items():
        parts.append(f"[시트: {sheet_name}]")
        parts.append(df.fillna("").astype(str).to_string(index=False, header=False))
    return "\n".join(parts)
