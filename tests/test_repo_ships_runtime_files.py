"""2026-10-03 VM 部署失敗：icon-180.png 被 .gitignore 的 *.png 擋掉，git pull 拿不到，server 啟動就讀檔失敗。
VM 只有 git 追蹤的檔案；程式在執行時讀的非 .py 檔都必須在 git 裡。"""
import subprocess
import pytest

RUNTIME_FILES = ["src/portfolio/render/icon-180.png", "vendor/echarts/echarts.min.js", "docs/eis-mcp-client-setup.md"]


@pytest.mark.parametrize("path", RUNTIME_FILES)
def test_runtime_file_is_tracked_by_git(path):
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", path], capture_output=True, text=True)
    assert tracked.returncode == 0, f"{path} is not in git (check .gitignore): {tracked.stderr.strip()}"


def test_missing_png_icon_does_not_stop_the_server(tmp_path):
    """讀不到 PNG 時只少 PNG 圖示，不可讓 import 失敗（server 會起不來）。"""
    from src.portfolio.render.icon import load_png
    assert load_png(tmp_path / "nope.png") is None
