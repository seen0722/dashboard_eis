# deploy/offline — 離線安裝用檔案（進版控，clone 即帶到）

給連不到 PyPI / 沒有 Python 3.12 的公司主機。`git clone` 或 `git pull` 之後不需要再傳任何檔案。

| 檔案 | 內容 | 大小 |
|---|---|---|
| `wheels/*.whl` | `requirements.txt` 的全部相依（Python 3.12 / x86_64 Linux 二進位 wheel，40 個） | 約 12 MB |
| `cpython-3.12.*-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz` | Python 3.12 本體（[python-build-standalone](https://github.com/astral-sh/python-build-standalone)，stripped 版；解壓即用，不需 apt） | 約 35 MB |

## 主機上怎麼用

```bash
cd dashboard_eis                                   # clone 下來的 repo 根目錄

# 1. 主機 python3 < 3.12 時：解一份 3.12 到 /opt/python3.12（不動系統 python）
sudo mkdir -p /opt/python3.12
sudo tar -xzf deploy/offline/cpython-3.12.*-install_only_stripped.tar.gz -C /opt/python3.12 --strip-components=1
/opt/python3.12/bin/python3.12 --version

# 2. 安裝：install.sh 看到 deploy/offline/wheels/ 就自動 --no-index，不碰 PyPI
PYTHON=/opt/python3.12/bin/python3.12 sudo -E deploy/install.sh
```

主機本身已有 3.12 時省略第 1 步，直接 `sudo deploy/install.sh`。

## 更新這些檔案（在能上網的機器）

```bash
# wheel：requirements.txt 變動後重抓
rm -rf deploy/offline/wheels && mkdir -p deploy/offline/wheels
python3 -m pip download -r requirements.txt -d deploy/offline/wheels \
  --python-version 3.12 --only-binary=:all: \
  --platform manylinux2014_x86_64 --platform manylinux_2_17_x86_64 --platform manylinux_2_28_x86_64 --platform any

# Python：換版本時從 astral-sh/python-build-standalone 的 release 抓 install_only_stripped 版
```

主機若是 ARM（`uname -m` = aarch64）或 Python 版本不同，wheel 與 tarball 都要換對應版本。
