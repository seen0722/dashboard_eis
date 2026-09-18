from src.eis_mcp.__main__ import main


def test_main_refuses_without_tokens_file(tmp_path, capsys):
    assert main(["--data", str(tmp_path / "d")]) == 1
    assert "tokens.yaml" in capsys.readouterr().err


def test_main_refuses_bad_permissions(tmp_path, capsys):
    d = tmp_path / "d"; d.mkdir()
    (d / "tokens.yaml").write_text("tokens:\n  - token: a\n    name: A\n    role: viewer\n"); (d / "tokens.yaml").chmod(0o644)
    assert main(["--data", str(d)]) == 1
    assert f"chmod 600 {d / 'tokens.yaml'}" in capsys.readouterr().err


def test_main_runs_uvicorn_with_args(tmp_path, monkeypatch):
    d = tmp_path / "d"; d.mkdir()
    (d / "tokens.yaml").write_text("tokens:\n  - token: a\n    name: A\n    role: viewer\n"); (d / "tokens.yaml").chmod(0o600)
    calls = {}
    monkeypatch.setattr("src.eis_mcp.__main__.uvicorn.run", lambda app, **kw: calls.update(kw, app=app))
    assert main(["--data", str(d), "--host", "10.0.0.5", "--port", "9000", "--allowed-host", "eis.example:9000"]) == 0
    assert calls["host"] == "10.0.0.5" and calls["port"] == 9000 and calls["app"].state.eis.store.root == d
