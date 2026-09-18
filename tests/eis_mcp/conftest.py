import pytest
from src.eis_mcp.store import Store
from tests.portfolio.test_cli import build_input


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "data"); s.init_layout()
    return s


@pytest.fixture
def input_pack(tmp_path):
    d = tmp_path / "pack"; d.mkdir(); build_input(d)
    return d
