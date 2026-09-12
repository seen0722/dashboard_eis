from pathlib import Path
import openpyxl
import pytest


def make_xlsx(path: Path, sheets: dict[str, list[list]]) -> Path:
    """sheets: {sheet_name: rows}. rows 是 list of list，None 代表空格。"""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for r in rows:
            ws.append(r)
    wb.save(path)
    return path


@pytest.fixture
def xlsx(tmp_path):
    def _make(name: str, sheets: dict[str, list[list]]) -> Path:
        return make_xlsx(tmp_path / name, sheets)
    return _make
