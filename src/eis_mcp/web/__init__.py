"""免登入、唯讀的網頁查詢介面（/ui/*）。掛在與 /mcp 同一支 Starlette app 上。"""
from .routes import register_routes  # noqa: F401
