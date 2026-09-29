"""Transient browser selections and progress; never persisted as credentials."""

import os
from typing import Any


RELOAD_TOKEN = os.environ.get("BILIBILI_RELOAD_TOKEN", "")
SELECTED_UID: str | None = None
QR_LOGIN: Any | None = None
PROGRESS: dict[str, Any] = {"running": False, "message": "Idle.", "percent": 0, "count": None}
