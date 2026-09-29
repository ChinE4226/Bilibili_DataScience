"""Browser creator selection and saved UP management."""

from __future__ import annotations

import json
from typing import Any

from bilibili_ds import config
from bilibili_ds.web import state


def normalize_web_up(entry: Any) -> dict[str, str] | None:
    if not isinstance(entry, dict):
        return None
    uid = str(entry.get("uid") or entry.get("mid") or "").strip()
    space = str(entry.get("space") or "").strip()
    name = str(entry.get("name") or entry.get("uname") or "").strip()
    if not uid and "space.bilibili.com/" in space:
        uid = space.rstrip("/").split("/")[-1]
    if not uid.isdigit():
        return None
    if not space:
        space = f"https://space.bilibili.com/{uid}"
    if not name:
        name = f"UP-{uid}"
    return {"name": name, "space": space, "uid": uid}


def load_web_ups() -> list[dict[str, str]]:
    try:
        raw = json.loads(config.UPS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return []

    entries = raw.get("ups", []) if isinstance(raw, dict) else raw
    if isinstance(entries, dict):
        entries = [entries]
    if not isinstance(entries, list):
        return []

    normalized = []
    seen = set()
    for entry in entries:
        up = normalize_web_up(entry)
        if up is None or up["uid"] in seen:
            continue
        normalized.append(up)
        seen.add(up["uid"])
    return normalized


def save_web_ups(entries: list[dict[str, str]]) -> None:
    seen = set()
    normalized = []
    for entry in entries:
        up = normalize_web_up(entry)
        if up is None or up["uid"] in seen:
            continue
        normalized.append(up)
        seen.add(up["uid"])
    config.UPS_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.UPS_FILE.write_text(json.dumps({"ups": normalized}, ensure_ascii=False, indent=2), encoding="utf-8")


def add_web_up(name: str, space: str) -> dict[str, str]:
    normalized = normalize_web_up({"name": name, "space": space})
    if normalized is None:
        raise ValueError("Cannot parse a valid Bilibili UID from that UP data.")
    entries = [entry for entry in load_web_ups() if entry["uid"] != normalized["uid"]]
    entries.append(normalized)
    save_web_ups(entries)
    select_up_by_uid(normalized["uid"])
    return normalized


def selected_up() -> dict[str, str] | None:
    ups = load_web_ups()
    if not ups:
        return None
    if state.SELECTED_UID is None:
        return ups[0]
    for entry in ups:
        if entry["uid"] == state.SELECTED_UID:
            return entry
    return ups[0]


def select_up_by_uid(uid: str) -> dict[str, str] | None:
    for entry in load_web_ups():
        if entry["uid"] == uid:
            state.SELECTED_UID = uid
            return entry
    return None
