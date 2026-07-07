"""다양한 데이터 형식 읽기 테스트 — read_uploaded_table"""
import io
import pandas as pd
from app.loaders.csv_loader import read_uploaded_table


class _Named(io.BytesIO):
    """name 속성을 가진 업로드 파일 흉내."""
    def __init__(self, data: bytes, name: str) -> None:
        super().__init__(data)
        self.name = name


def test_read_csv():
    df = read_uploaded_table(_Named(b"a,b\n1,2\n3,4", "data.csv"))
    assert list(df.columns) == ["a", "b"]
    assert len(df) == 2


def test_read_tsv():
    df = read_uploaded_table(_Named(b"a\tb\n1\t2", "data.tsv"))
    assert list(df.columns) == ["a", "b"]


def test_read_json():
    df = read_uploaded_table(_Named(b'[{"a":1,"b":2},{"a":3,"b":4}]', "data.json"))
    assert list(df.columns) == ["a", "b"]
    assert len(df) == 2


def test_read_excel():
    buf = io.BytesIO()
    pd.DataFrame({"a": [1, 2], "b": [3, 4]}).to_excel(buf, index=False)
    df = read_uploaded_table(_Named(buf.getvalue(), "data.xlsx"))
    assert list(df.columns) == ["a", "b"]
    assert len(df) == 2


def test_txt_falls_back_to_csv():
    df = read_uploaded_table(_Named(b"a,b\n1,2", "data.txt"))
    assert list(df.columns) == ["a", "b"]
