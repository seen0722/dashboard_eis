from pathlib import Path
import pytest
from src.portfolio.extract import workbook as wbmod


def test_xlsx_rows_and_sheetnames(xlsx):
    p = xlsx("a.xlsx", {"S1": [["h1", "h2"], [1, None]], "S2": [["x"]]})
    wb = wbmod.open_workbook(p)
    assert wb.sheetnames == ["S1", "S2"]
    assert list(wb.rows("S1")) == [("h1", "h2"), (1, None)]


def test_xlsb_dispatches_to_pyxlsb(monkeypatch, tmp_path):
    called = {}

    class FakeSheet:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def rows(self):
            class C:  # 模仿 pyxlsb Cell
                def __init__(self, v): self.v = v
            yield [C("h")]
            yield [C(3)]

    class FakeWb:
        sheets = ["Only"]
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get_sheet(self, name): called["name"] = name; return FakeSheet()

    monkeypatch.setattr(wbmod, "_open_xlsb", lambda path: FakeWb())
    p = tmp_path / "b.xlsb"; p.write_bytes(b"")
    wb = wbmod.open_workbook(p)
    assert wb.sheetnames == ["Only"]
    assert list(wb.rows("Only")) == [("h",), (3,)]
    assert called["name"] == "Only"


def test_unknown_extension_raises(tmp_path):
    p = tmp_path / "c.csv"; p.write_text("")
    with pytest.raises(ValueError):
        wbmod.open_workbook(p)


def test_xlsx_context_manager_and_idempotent_close(xlsx):
    p = xlsx("a.xlsx", {"S1": [["h1", "h2"], [1, None]]})
    with wbmod.open_workbook(p) as wb:
        assert wb.sheetnames == ["S1"]
        assert list(wb.rows("S1")) == [("h1", "h2"), (1, None)]
    # After exiting context, close() should have been called.
    # Calling close() again should be idempotent and not raise.
    wb.close()


def test_xlsb_close_releases_resource(monkeypatch, tmp_path):
    closed = {}

    class FakeSheet:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def rows(self):
            class C:
                def __init__(self, v): self.v = v
            yield [C("h")]

    class FakeWb:
        sheets = ["Only"]
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get_sheet(self, name): return FakeSheet()
        def close(self):
            closed["xlsb"] = True

    monkeypatch.setattr(wbmod, "_open_xlsb", lambda path: FakeWb())
    p = tmp_path / "b.xlsb"; p.write_bytes(b"")
    wb = wbmod.open_workbook(p)
    assert "xlsb" not in closed
    wb.close()
    assert closed.get("xlsb") == True
