"""JSON persistence, saved creators, and creator selection."""

import json
from pathlib import Path
import re
from typing import Any

from bilibili_ds import config, state


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_uid_from_space(space: str) -> int:
    match = re.search(r"space\.bilibili\.com/(\d+)", space)
    if not match:
        raise ValueError(f"Cannot parse Bilibili UID from {space!r}")
    return int(match.group(1))


def uid_from_up(entry: dict[str, Any]) -> int:
    if entry.get("uid"):
        return int(entry["uid"])
    return parse_uid_from_space(str(entry.get("space", "")))


def load_uid(object_file: Path) -> int:
    data = read_json(object_file, {})
    if isinstance(data, dict) and isinstance(data.get("ups"), list):
        if object_file.resolve() == config.UPS_FILE.resolve():
            selected_up = load_selected_up()
            if selected_up is not None:
                return uid_from_up(selected_up)
        ups = normalize_up_entries(data.get("ups", []))
        if ups:
            return uid_from_up(ups[0])
    if isinstance(data, list):
        ups = normalize_up_entries(data)
        if ups:
            return uid_from_up(ups[0])
    return uid_from_up(data)


def normalize_up(entry: dict[str, Any]) -> dict[str, str] | None:
    space = str(entry.get("space") or "").strip()
    if not space:
        uid = str(entry.get("uid") or entry.get("mid") or "").strip()
        if not uid.isdigit():
            return None
        space = f"https://space.bilibili.com/{uid}"

    try:
        uid = parse_uid_from_space(space)
    except ValueError:
        return None

    name = str(entry.get("name") or entry.get("uname") or f"UP-{uid}").strip()
    return {"name": name, "space": space, "uid": str(uid)}


def extract_ups_from_text(raw: str) -> list[dict[str, str]]:
    pattern = r'\{\s*"name"\s*:\s*"([^"]+)"\s*,\s*"space"\s*:\s*"([^"]+)"\s*\}'
    return [
        normalized
        for name, space in re.findall(pattern, raw)
        if (normalized := normalize_up({"name": name, "space": space})) is not None
    ]


def normalize_up_entries(entries: Any) -> list[dict[str, str]]:
    if isinstance(entries, dict):
        entries = [entries]
    if not isinstance(entries, list):
        return []
    return [
        normalized
        for entry in entries
        if isinstance(entry, dict)
        if (normalized := normalize_up(entry)) is not None
    ]


def merge_up_entries(entries: list[dict[str, str]]) -> list[dict[str, str]]:
    merged: dict[str, dict[str, str]] = {}
    for entry in entries:
        key = entry["uid"]
        if key not in merged or merged[key].get("name", "").startswith("UP-"):
            merged[key] = entry
    return sorted(merged.values(), key=lambda item: item["name"].lower())


def default_up_store() -> dict[str, Any]:
    return {"ups": []}


def load_up_store() -> dict[str, Any]:
    raw = read_json(config.UPS_FILE, default_up_store())
    if isinstance(raw, list):
        store = {"ups": normalize_up_entries(raw)}
    elif isinstance(raw, dict):
        if state.SELECTED_UID is None and raw.get("selected_uid"):
            state.SELECTED_UID = str(raw["selected_uid"])
        store = {"ups": normalize_up_entries(raw.get("ups", []))}
    else:
        store = default_up_store()

    store["ups"] = merge_up_entries(store["ups"])
    known_uids = {entry["uid"] for entry in store["ups"]}
    if state.SELECTED_UID not in known_uids:
        state.SELECTED_UID = store["ups"][0]["uid"] if store["ups"] else None
    write_json(config.UPS_FILE, store)
    return store


def save_up_store(store: dict[str, Any]) -> None:
    normalized_store = {"ups": merge_up_entries(normalize_up_entries(store.get("ups", [])))}
    known_uids = {entry["uid"] for entry in normalized_store["ups"]}
    if state.SELECTED_UID not in known_uids:
        state.SELECTED_UID = normalized_store["ups"][0]["uid"] if normalized_store["ups"] else None
    write_json(config.UPS_FILE, normalized_store)


def load_ups() -> list[dict[str, str]]:
    return load_up_store()["ups"]


def save_ups(entries: list[dict[str, str]]) -> None:
    store = load_up_store()
    store["ups"] = merge_up_entries(entries)
    save_up_store(store)


def load_selected_up() -> dict[str, str] | None:
    store = load_up_store()
    for entry in store["ups"]:
        if entry["uid"] == state.SELECTED_UID:
            return entry
    return None


def save_selected_up(entry: dict[str, str]) -> None:
    normalized = normalize_up(entry)
    if normalized is None:
        raise ValueError("Cannot save an invalid UP entry.")
    store = load_up_store()
    store["ups"] = merge_up_entries([*store["ups"], normalized])
    state.SELECTED_UID = normalized["uid"]
    save_up_store(store)


def selected_up_summary() -> str:
    selected_up = load_selected_up()
    if selected_up is None:
        return "None"
    return f"{selected_up['name']} (UID {selected_up['uid']})"
