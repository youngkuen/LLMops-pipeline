"""개인정보 탐지·마스킹 단위 테스트 — Data Layer"""
import pandas as pd
from app.loaders.anonymizer import detect_pii_columns, mask_text, mask_value


def test_detects_pii_by_column_name():
    df = pd.DataFrame({"email": ["a@x.com"], "age": [25]})
    pii = detect_pii_columns(df, ["email", "age"])
    assert pii == {"email": "email"}


def test_detects_pii_by_value_pattern_when_column_name_is_ambiguous():
    df = pd.DataFrame({"contact_info": ["010-1234-5678", "010-2222-3333"]})
    pii = detect_pii_columns(df, ["contact_info"])
    assert pii == {"contact_info": "phone"}


def test_ignores_column_with_no_pii_signal():
    df = pd.DataFrame({"score": [10, 20, 30]})
    assert detect_pii_columns(df, ["score"]) == {}


def test_partial_match_below_threshold_is_ignored():
    # 10개 중 1개만 이메일 패턴 — 임계치(50%) 미달이라 탐지되지 않아야 함
    df = pd.DataFrame({"note": ["a@x.com"] + ["일반 텍스트"] * 9})
    assert detect_pii_columns(df, ["note"]) == {}


def test_mask_value_email():
    assert mask_value("hong@example.com", "email") == "h***@example.com"


def test_mask_value_phone():
    assert mask_value("010-1234-5678", "phone") == "010-****-5678"


def test_mask_value_resident_id():
    assert mask_value("901231-1234567", "resident_id") == "901231-*******"


def test_mask_value_card():
    assert mask_value("1234-5678-9012-3456", "card") == "****-****-****-3456"


def test_mask_value_name():
    assert mask_value("홍길동", "name") == "홍**"


def test_mask_text_redacts_embedded_values():
    text = "담당자 이메일은 hong@example.com이고 연락처는 010-1234-5678입니다."
    masked = mask_text(text)
    assert "hong@example.com" not in masked
    assert "010-1234-5678" not in masked
    assert "담당자 이메일은" in masked  # 설명 텍스트 자체는 보존


def test_mask_text_leaves_normal_text_untouched():
    text = "age: 고객 나이, income: 월 소득"
    assert mask_text(text) == text
