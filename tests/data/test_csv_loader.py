"""T-004 검증 — CSV 로더 + DataSchema 추론 테스트"""
import os
import tempfile
import pytest
import pandas as pd
from app.loaders.csv_loader import infer_schema, load_dataframe

SAMPLE_CSV = """age,income,city,survived
25,50000,Seoul,0
30,60000,Busan,1
35,70000,Seoul,1
40,80000,Daegu,0
"""


@pytest.fixture()
def csv_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write(SAMPLE_CSV)
        path = f.name
    yield path
    os.unlink(path)


def test_load_dataframe_returns_correct_shape(csv_file):
    df = load_dataframe(csv_file)
    assert df.shape == (4, 4)


def test_load_dataframe_raises_on_empty_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("col1,col2\n")
        path = f.name
    try:
        with pytest.raises(ValueError, match="비어 있습니다"):
            load_dataframe(path)
    finally:
        os.unlink(path)


def test_infer_schema_column_count(csv_file):
    df = load_dataframe(csv_file)
    schema = infer_schema(df)
    assert len(schema.columns) == 4


def test_infer_schema_numeric_detection(csv_file):
    df = load_dataframe(csv_file)
    schema = infer_schema(df)
    age_col = next(c for c in schema.columns if c.name == "age")
    assert age_col.data_type == "NUMERIC"


def test_infer_schema_categorical_detection(csv_file):
    df = load_dataframe(csv_file)
    schema = infer_schema(df)
    city_col = next(c for c in schema.columns if c.name == "city")
    assert city_col.data_type == "CATEGORICAL"


def test_infer_schema_origin_is_inferred(csv_file):
    df = load_dataframe(csv_file)
    schema = infer_schema(df)
    assert schema.origin == "INFERRED"
