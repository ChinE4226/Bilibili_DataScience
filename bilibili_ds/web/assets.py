"""Dashboard template rendering and confined public asset lookup."""

from html import escape
from pathlib import Path
from urllib.parse import unquote

from bilibili_ds import config
from bilibili_ds.web import state


STATIC_CONTENT_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
}


def dashboard_html() -> bytes:
    template = (config.TEMPLATES_DIR / "dashboard.html").read_text(encoding="utf-8")
    return template.replace("__DEV_RELOAD_TOKEN__", escape(state.RELOAD_TOKEN, quote=True)).encode("utf-8")


def static_file(raw_name: str) -> Path | None:
    try:
        root = config.STATIC_DIR.resolve()
        path = (root / unquote(raw_name)).resolve()
        if root not in path.parents or path.suffix not in STATIC_CONTENT_TYPES or not path.is_file():
            return None
        return path
    except (OSError, ValueError):
        return None
