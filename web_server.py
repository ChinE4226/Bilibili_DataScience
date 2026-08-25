#!/usr/bin/env python3
"""Local web server for the Bilibili Data Science project."""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import mimetypes
import re
import subprocess
import webbrowser
import statistics
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


PROJECT_ROOT = Path(__file__).resolve().parent
MAIN_FILE = PROJECT_ROOT / "main" / "main.py"
UPS_FILE = PROJECT_ROOT / "objects" / "ups.json"
RUNTIME_DIR = PROJECT_ROOT / ".runtime"
PLOTS_DIR = RUNTIME_DIR / "plots"
ACTIVE_ACCOUNT_FILE = RUNTIME_DIR / "active_account.json"
DEFAULT_REQUEST_FREQUENCY = 4.0
REQUEST_FREQUENCY = DEFAULT_REQUEST_FREQUENCY
SELECTED_UID: str | None = None
QR_LOGIN: Any | None = None
PROGRESS: dict[str, Any] = {"running": False, "message": "Idle.", "percent": 0, "count": None}

VIDEO_FIELDS = [
    {"field": "views", "label": "Views", "stat_key": "view"},
    {"field": "likes", "label": "Likes", "stat_key": "like"},
    {"field": "replies", "label": "Replies", "stat_key": "reply"},
    {"field": "favorites", "label": "Favorites", "stat_key": "favorite"},
    {"field": "coins", "label": "Coins", "stat_key": "coin"},
    {"field": "shares", "label": "Shares", "stat_key": "share"},
]


def load_terminal_app() -> Any:
    spec = importlib.util.spec_from_file_location("bilibili_terminal_app", MAIN_FILE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {MAIN_FILE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


APP = load_terminal_app()
from matplotlib import dates as mdates
from matplotlib import ticker


def json_bytes(data: Any) -> bytes:
    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")


def set_progress(message: str, *, running: bool | None = None, percent: int | None = None, count: int | None = None) -> None:
    if running is not None:
        PROGRESS["running"] = running
    PROGRESS["message"] = message
    if percent is not None:
        PROGRESS["percent"] = max(0, min(100, percent))
    if count is not None:
        PROGRESS["count"] = count


def read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length") or 0)
    if length <= 0:
        return {}
    if length > 64 * 1024:
        raise ValueError("Request body is too large.")
    try:
        body = handler.rfile.read(length).decode("utf-8")
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValueError("Request body must be valid JSON.") from exc
    if not isinstance(data, dict):
        raise ValueError("Request body must be a JSON object.")
    return data


def plot_entries() -> list[dict[str, Any]]:
    if not PLOTS_DIR.exists():
        return []

    entries = []
    for path in sorted(PLOTS_DIR.glob("*.png"), key=lambda item: item.stat().st_mtime, reverse=True):
        stat = path.stat()
        entries.append(
            {
                "name": path.name,
                "url": f"/plots/{path.name}",
                "size": stat.st_size,
                "modified": int(stat.st_mtime),
            }
        )
    return entries


def plot_file_path(selected: dict[str, str], plot_label: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_up_name = re.sub(r"[^\w.-]+", "_", selected.get("name", ""), flags=re.UNICODE).strip("_")[:40]
    up_part = f"{safe_up_name}_{selected['uid']}" if safe_up_name else selected["uid"]
    safe_label = re.sub(r"[^\w.-]+", "_", plot_label, flags=re.UNICODE).strip("_")[:80] or "plot"
    return PLOTS_DIR / f"{up_part}_{timestamp}_{safe_label}.png"


def save_web_plot_png(
    selected: dict[str, str],
    selection_label: str,
    plot_label: str,
    y_label: str,
    points: list[dict[str, Any]],
) -> str | None:
    if not points:
        return None

    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = plot_file_path(selected, plot_label)
    parsed_dates = [
        datetime.strptime(str(point["label"]), "%Y-%m-%d %H:%M:%S")
        for point in points
        if re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", str(point["label"]))
    ]
    x_values = parsed_dates if len(parsed_dates) == len(points) else list(range(1, len(points) + 1))
    y_values = [float(point["value"]) for point in points]
    y_min = min(y_values)
    y_max = max(y_values)
    y_spread = y_max - y_min
    y_pad = max(y_spread * 0.12, abs(y_max) * 0.03, 1.0) if y_spread else max(abs(y_max) * 0.12, 1.0)

    figure, axis = APP.plt.subplots(figsize=(13, 7))
    axis.plot(x_values, y_values, marker="o", linewidth=2.0, markersize=4.5)
    axis.set_title(f"{selected['name']} (UID {selected['uid']}) - {plot_label}")
    axis.set_xlabel("Published time")
    axis.set_ylabel(y_label)
    axis.set_ylim(y_min - y_pad, y_max + y_pad)
    axis.margins(x=0.03)
    axis.grid(True, linewidth=0.5, alpha=0.5)
    axis.yaxis.set_major_locator(ticker.MaxNLocator(nbins=7))
    axis.yaxis.set_major_formatter(ticker.StrMethodFormatter("{x:,.2f}"))
    if x_values and isinstance(x_values[0], datetime):
        axis.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=8))
        axis.xaxis.set_major_formatter(mdates.ConciseDateFormatter(axis.xaxis.get_major_locator()))
    else:
        step = max(1, len(points) // 8)
        ticks = x_values[::step]
        labels = [str(point["label"])[:10] for point in points]
        axis.set_xticks(ticks)
        axis.set_xticklabels(labels[::step], rotation=30, ha="right")
    axis.text(
        0.01,
        0.99,
        selection_label,
        transform=axis.transAxes,
        va="top",
        ha="left",
        fontsize=8,
        bbox={"boxstyle": "round,pad=0.25", "facecolor": "white", "alpha": 0.75, "edgecolor": "#cccccc"},
    )
    figure.autofmt_xdate()
    figure.tight_layout()
    figure.savefig(output_path, dpi=160)
    APP.plt.close(figure)
    return output_path.name


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
        raw = json.loads(UPS_FILE.read_text(encoding="utf-8"))
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
    UPS_FILE.parent.mkdir(parents=True, exist_ok=True)
    UPS_FILE.write_text(json.dumps({"ups": normalized}, ensure_ascii=False, indent=2), encoding="utf-8")


def add_web_up(name: str, space: str) -> dict[str, str]:
    normalized = normalize_web_up({"name": name, "space": space})
    if normalized is None:
        raise ValueError("Cannot parse a valid Bilibili UID from that UP data.")
    entries = [entry for entry in load_web_ups() if entry["uid"] != normalized["uid"]]
    entries.append(normalized)
    save_web_ups(entries)
    select_up_by_uid(normalized["uid"])
    return normalized


def account_summary() -> str:
    try:
        raw = json.loads(ACTIVE_ACCOUNT_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return "Guest mode"
    account_id = raw.get("id") if isinstance(raw, dict) else None
    if account_id:
        return f"Account {account_id} (UID {account_id})"
    return "Guest mode"


def selected_up() -> dict[str, str] | None:
    ups = load_web_ups()
    if not ups:
        return None
    if SELECTED_UID is None:
        return ups[0]
    for entry in ups:
        if entry["uid"] == SELECTED_UID:
            return entry
    return ups[0]


def select_up_by_uid(uid: str) -> dict[str, str] | None:
    global SELECTED_UID

    for entry in load_web_ups():
        if entry["uid"] == uid:
            SELECTED_UID = uid
            return entry
    return None


def field_by_name(name: str, *, allow_followers: bool = False) -> dict[str, str] | None:
    for field in VIDEO_FIELDS:
        if name == field["field"] or name == field["stat_key"]:
            return field
    if allow_followers and name == "followers":
        return {"field": "followers", "label": "Followers", "source": "followers"}
    return None


def int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_range_number(value: Any) -> int | None:
    if value in (None, ""):
        return None
    text = str(value).strip().lower().replace(",", "").replace(" ", "")
    multiplier = 1
    if text.endswith("k"):
        multiplier = 1_000
        text = text[:-1]
    elif text.endswith("m"):
        multiplier = 1_000_000
        text = text[:-1]
    try:
        number = float(text)
    except ValueError:
        return None
    if number < 0:
        return None
    return int(number * multiplier)


def video_timestamp(item: dict[str, Any]) -> int | None:
    return int_or_none(item.get("pubdate") or item.get("created"))


def video_metric(item: dict[str, Any], stat_key: str) -> int | None:
    stat = item.get("stat") if isinstance(item.get("stat"), dict) else {}
    return int_or_none(stat.get(stat_key))


def format_time(timestamp: int | None) -> str:
    if timestamp is None:
        return "Unknown"
    try:
        return APP.datetime.fromtimestamp(timestamp).isoformat(sep=" ")
    except Exception:
        return str(timestamp)


def serialize_video(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": item.get("title") or "(no title)",
        "bvid": item.get("bvid"),
        "aid": item.get("aid"),
        "published_time": format_time(video_timestamp(item)),
        "published_timestamp": video_timestamp(item),
        "views": video_metric(item, "view"),
        "likes": video_metric(item, "like"),
        "replies": video_metric(item, "reply"),
        "favorites": video_metric(item, "favorite"),
        "coins": video_metric(item, "coin"),
        "shares": video_metric(item, "share"),
    }


def sort_by_published_time(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=lambda item: video_timestamp(item) or 0)


def field_value(item: dict[str, Any], field: dict[str, str], followers: int | None = None) -> int | None:
    if field.get("source") == "followers":
        return followers
    return video_metric(item, field["stat_key"])


def ratio_value(
    item: dict[str, Any],
    numerator: dict[str, str],
    denominator: dict[str, str],
    followers: int | None,
) -> float | None:
    numerator_value = field_value(item, numerator, followers)
    denominator_value = field_value(item, denominator, followers)
    if numerator_value is None or denominator_value in (None, 0):
        return None
    return numerator_value / denominator_value


async def fetch_web_video_summaries(
    uploader: Any,
    target_count: int,
    order: Any,
    *,
    progress_label: str,
    start_percent: int,
    end_percent: int,
) -> list[dict[str, Any]]:
    page_size = 30
    page_number = 1
    fetched_items: list[dict[str, Any]] = []
    total_pages = max(1, (target_count + page_size - 1) // page_size)

    while len(fetched_items) < target_count:
        percent = start_percent + int((len(fetched_items) / max(target_count, 1)) * (end_percent - start_percent))
        set_progress(
            f"{progress_label}: page {page_number}/{total_pages}, {len(fetched_items)}/{target_count} summaries fetched.",
            percent=percent,
            count=len(fetched_items),
        )
        try:
            page_data = await uploader.get_videos(pn=page_number, ps=page_size, order=order)
        except Exception as exc:
            set_progress(f"Failed to fetch video summary page {page_number}: {exc}", percent=percent)
            break

        page_items = page_data.get("list", {}).get("vlist", [])
        if not page_items:
            break

        fetched_items.extend(page_items[: target_count - len(fetched_items)])
        set_progress(
            f"{progress_label}: {len(fetched_items)}/{target_count} summaries fetched.",
            percent=start_percent + int((len(fetched_items) / max(target_count, 1)) * (end_percent - start_percent)),
            count=len(fetched_items),
        )
        page_number += 1
        await asyncio.sleep(APP.request_delay_seconds())

    return fetched_items


async def enrich_web_video_items(
    items: list[dict[str, Any]],
    credential: Any,
    *,
    progress_label: str,
    start_percent: int,
    end_percent: int,
) -> list[dict[str, Any]]:
    enriched_items: list[dict[str, Any]] = []
    total = len(items)
    if total == 0:
        set_progress(f"{progress_label}: no video details to fetch.", percent=end_percent, count=0)
        return enriched_items

    for index, item in enumerate(items, start=1):
        set_progress(
            f"{progress_label}: fetching detail {index}/{total}.",
            percent=start_percent + int(((index - 1) / total) * (end_percent - start_percent)),
            count=index - 1,
        )
        enriched_items.append(await APP.fetch_video_detail(item, credential))
        set_progress(
            f"{progress_label}: fetched detail {index}/{total}.",
            percent=start_percent + int((index / total) * (end_percent - start_percent)),
            count=index,
        )
        await asyncio.sleep(APP.request_delay_seconds())

    return enriched_items


async def fetch_selected_video_items(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], str, int | None]:
    selected = selected_up()
    if selected is None:
        raise ValueError("No UP is selected.")

    credential = APP.credential_from_env()
    uploader = APP.user.User(int(selected["uid"]), credential=credential)
    selection = payload.get("selection") if isinstance(payload.get("selection"), dict) else {}
    kind = selection.get("kind") or "latest"
    action = str(payload.get("action") or "video")
    action_label = {"list": "Listing", "analysis": "Analysis", "division": "Division", "plot": "Plotting"}.get(action, "Video action")

    APP.REQUEST_FREQUENCY = REQUEST_FREQUENCY
    APP.configure_bilibili_client()
    try:
        set_progress(f"{action_label}: checking selected UP video count.", running=True, percent=5, count=0)
        first_page = await uploader.get_videos(pn=1, ps=1, order=APP.user.VideoOrder.PUBDATE)
        total = APP.video_total_from_response(first_page)
        if total <= 0:
            set_progress("No videos were found for the selected UP.", running=False, percent=100, count=0)
            return [], "no videos", None

        if kind == "position":
            start = max(int(selection.get("start") or 1), 1)
            end = min(int(selection.get("end") or start), total)
            if start > end:
                raise ValueError("Start number must be smaller than or equal to end number.")
            summaries = await fetch_web_video_summaries(
                uploader,
                end,
                APP.user.VideoOrder.PUBDATE,
                progress_label=f"{action_label}: fetching video summaries {start}-{end} of {total}",
                start_percent=15,
                end_percent=50,
            )
            selected_summaries = summaries[start - 1 : end]
            items = await enrich_web_video_items(
                selected_summaries,
                credential,
                progress_label=f"{action_label}: fetching selected video details",
                start_percent=55,
                end_percent=88,
            )
            set_progress(f"Selected {len(items)} video(s).", percent=90, count=len(items))
            return sort_by_published_time(items), f"published-time positions {start}-{end}", total

        summaries = await fetch_web_video_summaries(
            uploader,
            total,
            APP.user.VideoOrder.PUBDATE,
            progress_label=f"{action_label}: fetching summaries for all {total} video(s)",
            start_percent=15,
            end_percent=50,
        )

        if kind == "published":
            start_raw = str(selection.get("start_time") or "").strip()
            end_raw = str(selection.get("end_time") or "").strip()
            if not start_raw or not end_raw:
                raise ValueError("Start time and end time are required.")
            start_dt = APP.parse_datetime_input(start_raw)
            end_dt = APP.parse_datetime_input(end_raw, end_of_day=True)
            if start_dt is None or end_dt is None:
                raise ValueError("Use YYYY-MM-DD or YYYY-MM-DD HH:MM:SS for time ranges.")
            start_ts = int(start_dt.timestamp())
            end_ts = int(end_dt.timestamp())
            selected_summaries = [
                item
                for item in summaries
                if (timestamp := video_timestamp(item)) is not None
                if start_ts <= timestamp <= end_ts
            ]
            items = await enrich_web_video_items(
                selected_summaries,
                credential,
                progress_label=f"{action_label}: fetching details for videos in the time range",
                start_percent=60,
                end_percent=88,
            )
            set_progress(f"Selected {len(items)} video(s).", percent=90, count=len(items))
            return sort_by_published_time(items), f"published time {start_raw} to {end_raw}", total

        if kind == "metric":
            field = field_by_name(str(selection.get("metric") or "views"))
            if field is None:
                raise ValueError("Invalid metric field.")
            minimum = parse_range_number(selection.get("minimum"))
            maximum = parse_range_number(selection.get("maximum"))
            if minimum is None and maximum is None:
                raise ValueError("Enter at least one metric boundary.")
            items = await enrich_web_video_items(
                summaries,
                credential,
                progress_label=f"{action_label}: fetching details before metric filtering",
                start_percent=55,
                end_percent=85,
            )
            filtered = [
                item
                for item in items
                if (value := video_metric(item, field["stat_key"])) is not None
                if minimum is None or value > minimum
                if maximum is None or value < maximum
            ]
            set_progress(f"Selected {len(filtered)} video(s) after metric filtering.", percent=90, count=len(filtered))
            return sort_by_published_time(filtered), f"{field['label']} range", total

        raise ValueError("Invalid video selection mode.")
    finally:
        await APP.close_bilibili_client()


async def fetch_followers() -> int | None:
    selected = selected_up()
    if selected is None:
        return None
    credential = APP.credential_from_env()
    uploader = APP.user.User(int(selected["uid"]), credential=credential)
    APP.configure_bilibili_client()
    try:
        relation = await uploader.get_relation_info()
        return int_or_none(relation.get("follower"))
    finally:
        await APP.close_bilibili_client()


def analyse_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    for field in VIDEO_FIELDS:
        values = [
            value
            for item in items
            if (value := video_metric(item, field["stat_key"])) is not None
        ]
        summaries.append(
            {
                "label": field["label"],
                "count": len(values),
                "mean": statistics.mean(values) if values else None,
                "median": statistics.median(values) if values else None,
            }
        )
    return summaries


def account_records_summary() -> list[dict[str, Any]]:
    records = APP.load_account_records()
    active = APP.active_account_id()
    return [
        {
            "id": record["id"],
            "name": record.get("name"),
            "uid": record.get("uid"),
            "source": record.get("source"),
            "active": record["id"] == active,
        }
        for record in records
    ]


def select_account(account_id: str) -> dict[str, Any]:
    for record in APP.load_account_records():
        if record["id"] == account_id:
            APP.write_json(ACTIVE_ACCOUNT_FILE, {"id": account_id})
            return {
                "id": record["id"],
                "name": record.get("name"),
                "uid": record.get("uid"),
                "source": record.get("source"),
            }
    raise ValueError("Account was not found.")


async def start_qr_sign_in() -> dict[str, Any]:
    global QR_LOGIN

    QR_LOGIN = APP.QrCodeLogin()
    await QR_LOGIN.generate_qrcode()
    APP.QRCODE_FILE.parent.mkdir(parents=True, exist_ok=True)
    QR_LOGIN.get_qrcode_picture().to_file(str(APP.QRCODE_FILE))
    return {"qr_code_url": "/runtime/qrcode.png", "status": "waiting"}


async def qr_sign_in_status() -> dict[str, Any]:
    global QR_LOGIN

    if QR_LOGIN is None:
        return {"status": "not_started"}
    event = await QR_LOGIN.check_state()
    if event == APP.QrCodeLoginEvents.DONE:
        credential = QR_LOGIN.get_credential()
        record = await APP.build_account_record(credential, source="qr")
        APP.save_account_record(record)
        QR_LOGIN = None
        return {"status": "done", "account": {"id": record["id"], "name": record["name"], "uid": record["uid"]}}
    if event == APP.QrCodeLoginEvents.TIMEOUT:
        QR_LOGIN = None
        return {"status": "timeout"}
    return {"status": "waiting"}


async def selected_up_detail() -> dict[str, Any]:
    selected = selected_up()
    if selected is None:
        raise ValueError("No UP is selected.")
    credential = APP.credential_from_env()
    uploader = APP.user.User(int(selected["uid"]), credential=credential)
    APP.configure_bilibili_client()
    try:
        info = await uploader.get_user_info()
        relation = await uploader.get_relation_info()
        first_page = await uploader.get_videos(pn=1, ps=1, order=APP.user.VideoOrder.PUBDATE)
        return {
            "selected": selected,
            "profile": info,
            "relation": relation,
            "video_total": APP.video_total_from_response(first_page),
        }
    finally:
        await APP.close_bilibili_client()


async def account_detail() -> dict[str, Any]:
    valid, detail, error = await APP.load_account_detail(APP.credential_from_env())
    if error:
        raise ValueError(error)
    if not valid or detail is None:
        raise ValueError("No valid signed-in account is available.")
    return detail


async def execute_video_action(payload: dict[str, Any]) -> dict[str, Any]:
    action = str(payload.get("action") or "")
    set_progress(f"Starting {action or 'video'} action.", running=True, percent=1, count=0)
    try:
        items, selection_label, total = await fetch_selected_video_items(payload)
        serialized = [serialize_video(item) for item in items]

        if action == "list":
            set_progress(f"List completed. Selected {len(items)} video(s).", running=False, percent=100, count=len(items))
            return {
                "action": action,
                "selection": selection_label,
                "total_videos": total,
                "count": len(items),
                "videos": serialized,
            }

        if action == "analysis":
            set_progress("Calculating mean and median.", percent=95, count=len(items))
            result = {
                "action": action,
                "selection": selection_label,
                "count": len(items),
                "summaries": analyse_items(items),
            }
            set_progress(f"Analysis completed. Selected {len(items)} video(s).", running=False, percent=100, count=len(items))
            return result

        if action in {"division", "plot"}:
            numerator = field_by_name(str(payload.get("numerator") or "likes"), allow_followers=True)
            denominator = field_by_name(str(payload.get("denominator") or "views"), allow_followers=True)
            if numerator is None or denominator is None:
                raise ValueError("Invalid numerator or denominator.")
            if "followers" in {numerator["field"], denominator["field"]}:
                set_progress("Fetching selected UP follower count.", percent=92, count=len(items))
                followers = await fetch_followers()
            else:
                followers = None

            if action == "division":
                mode = str(payload.get("mode") or "single")
                set_progress("Calculating division result.", percent=96, count=len(items))
                if mode == "aggregate":
                    numerator_values = [field_value(item, numerator, followers) for item in items]
                    denominator_values = [field_value(item, denominator, followers) for item in items]
                    numerator_total = sum(value for value in numerator_values if value is not None)
                    denominator_total = sum(value for value in denominator_values if value is not None)
                    ratio = None if denominator_total == 0 else numerator_total / denominator_total
                    result = {
                        "action": action,
                        "mode": mode,
                        "selection": selection_label,
                        "count": len(items),
                        "numerator_total": numerator_total,
                        "denominator_total": denominator_total,
                        "ratio": ratio,
                    }
                    set_progress(f"Division completed. Selected {len(items)} video(s).", running=False, percent=100, count=len(items))
                    return result
                rows = []
                for item, video_data in zip(items, serialized):
                    numerator_value = field_value(item, numerator, followers)
                    denominator_value = field_value(item, denominator, followers)
                    ratio = ratio_value(item, numerator, denominator, followers)
                    rows.append(
                        {
                            "title": video_data["title"],
                            "published_time": video_data["published_time"],
                            "numerator": numerator_value,
                            "denominator": denominator_value,
                            "ratio": ratio,
                        }
                    )
                result = {
                    "action": action,
                    "mode": mode,
                    "selection": selection_label,
                    "count": len(items),
                    "rows": rows,
                }
                set_progress(f"Division completed. Selected {len(items)} video(s).", running=False, percent=100, count=len(items))
                return result

            plot_mode = str(payload.get("plot_mode") or "field")
            points = []
            set_progress("Preparing plot points.", percent=96, count=len(items))
            if plot_mode == "field":
                field = field_by_name(str(payload.get("field") or "views"))
                if field is None:
                    raise ValueError("Invalid plot field.")
                plot_label = field["label"]
                y_label = field["label"]
                for item, video_data in zip(items, serialized):
                    value = field_value(item, field, None)
                    if value is None:
                        continue
                    points.append(
                        {
                            "title": video_data["title"],
                            "label": video_data["published_time"],
                            "value": value,
                        }
                    )
            else:
                plot_label = f"{numerator['label']} divided by {denominator['label']}"
                y_label = f"{numerator['label']} / {denominator['label']}"
                for item, video_data in zip(items, serialized):
                    value = ratio_value(item, numerator, denominator, followers)
                    if value is None:
                        continue
                    points.append(
                        {
                            "title": video_data["title"],
                            "label": video_data["published_time"],
                            "value": value,
                        }
                    )
            selected = selected_up()
            plot_file = save_web_plot_png(selected, selection_label, plot_label, y_label, points) if selected else None
            set_progress(f"Plot completed. Selected {len(items)} video(s), plotted {len(points)} point(s).", running=False, percent=100, count=len(items))
            return {
                "action": action,
                "selection": selection_label,
                "count": len(items),
                "points": points,
                "plot_file": plot_file,
                "plot_label": plot_label,
                "y_label": y_label,
            }

        raise ValueError("Invalid action.")
    except Exception as exc:
        set_progress(f"Failed: {exc}", running=False)
        raise


def sign_out_web(mode: str) -> dict[str, Any]:
    removed = 0
    if mode == "keep":
        try:
            ACTIVE_ACCOUNT_FILE.unlink()
            removed += 1
        except FileNotFoundError:
            pass
        return {"mode": mode, "removed": removed}
    if mode == "selected":
        removed = APP.clear_active_account_cache()
        return {"mode": mode, "removed": removed}
    if mode == "all":
        removed = APP.clear_all_account_caches()
        return {"mode": mode, "removed": removed}
    raise ValueError("Invalid sign-out mode.")


def dashboard_html() -> bytes:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Bilibili Data Science</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f4f4f4;
      --panel: #ffffff;
      --text: #111111;
      --muted: #666666;
      --line: #d0d0d0;
      --accent: #111111;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--text);
      background: var(--bg);
    }
    header, nav, section { background: var(--panel); border-bottom: 1px solid var(--line); }
    header { padding: 20px 28px; }
    h1, h2, h3 { margin: 0; }
    h1 { font-size: 22px; font-weight: 650; }
    h2 { font-size: 16px; font-weight: 650; }
    h3 { font-size: 14px; font-weight: 650; margin: 16px 0 8px; }
    nav {
      display: flex;
      gap: 8px;
      padding: 12px 28px;
      position: sticky;
      top: 0;
      z-index: 2;
    }
    nav button {
      min-width: 92px;
      min-height: 36px;
    }
    main { display: grid; grid-template-columns: 340px minmax(0, 1fr); gap: 16px; padding: 16px; }
    section {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      margin-bottom: 16px;
    }
    .muted { color: var(--muted); }
    .stack { display: grid; align-content: start; }
    .work { min-width: 0; }
    .grid { display: grid; gap: 12px; }
    .row { display: flex; flex-wrap: wrap; gap: 12px; align-items: end; }
    .nav-settings { margin-left: auto; }
    .actions { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin-top: 12px; }
    label { display: grid; gap: 4px; color: var(--muted); }
    input, select {
      min-height: 34px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 6px 8px;
      background: #ffffff;
      color: var(--text);
      font: inherit;
    }
    .detail-box {
      width: 100%;
      height: 300px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px;
      background: #ffffff;
      color: #111111;
      overflow: auto;
    }
    .up-list { display: grid; gap: 8px; max-height: 540px; overflow: auto; }
    .up {
      display: grid;
      gap: 8px;
      padding: 10px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fafafa;
    }
    .up.active { border-color: #111111; background: #eeeeee; }
    button {
      width: fit-content;
      border: 1px solid var(--accent);
      border-radius: 6px;
      background: #ffffff;
      color: #111111;
      padding: 7px 11px;
      margin: 6px 6px 6px 0;
      cursor: pointer;
      font: inherit;
    }
    nav button { margin: 0; }
    .panel > button { margin-top: 14px; }
    .panel > .row + button { margin-top: 16px; }
    button:hover { background: #eeeeee; }
    button[aria-current="page"] { background: #eeeeee; }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    th, td {
      border-bottom: 1px solid var(--line);
      padding: 7px 8px;
      text-align: left;
      vertical-align: top;
    }
    th { background: #eeeeee; }
    code {
      padding: 2px 5px;
      border-radius: 4px;
      background: #eeeeee;
    }
    .chart {
      width: 100%;
      min-height: 320px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
      margin-top: 12px;
      overflow: hidden;
    }
    svg { display: block; width: 100%; height: 360px; }
    .panel { display: none; }
    .panel.active { display: block; }
    .result { overflow: auto; max-height: 640px; }
    .progress {
      min-height: 34px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 7px 9px;
      margin-top: 12px;
      background: #fafafa;
      color: var(--muted);
    }
    .panel-progress {
      margin: 10px 0 12px;
    }
    .plot-field-control[hidden],
    .plot-quotient-control[hidden] { display: none !important; }
    .saved-plots-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 420px));
      gap: 14px;
      align-items: start;
    }
    .saved-plot {
      display: grid;
      gap: 8px;
      padding: 10px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fafafa;
    }
    .saved-plot img {
      display: block;
      width: 100%;
      max-height: 260px;
      object-fit: contain;
      border: 1px solid var(--line);
      background: #ffffff;
    }
    .saved-plot footer {
      display: grid;
      gap: 4px;
      color: var(--muted);
      overflow-wrap: anywhere;
    }
    #qr-result img { max-width: 220px; height: auto; }
    [hidden] { display: none !important; }
    @media (max-width: 820px) {
      main { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Bilibili Data Science</h1>
    <div id="status" class="muted">Loading...</div>
  </header>
  <nav>
    <button data-panel="up" aria-current="page">UP Detail</button>
    <button data-panel="videos">Videos</button>
    <button data-panel="analysis">Analysis</button>
    <button data-panel="division">Division</button>
    <button data-panel="plot">Plot</button>
    <button data-panel="saved-plots">Saved Plots</button>
    <button class="nav-settings" data-panel="settings">Settings</button>
  </nav>
  <main>
    <div class="stack">
      <section>
        <h2>Selected UP</h2>
        <div id="selected" class="muted">Loading...</div>
      </section>
      <section>
        <h2>Add UP</h2>
        <div class="grid">
          <label>Name <input id="new-up-name" placeholder="Display name"></label>
          <label>Space URL or UID <input id="new-up-space" placeholder="https://space.bilibili.com/12345"></label>
          <button id="add-up">Add and Select</button>
        </div>
      </section>
      <section>
        <h2>Saved UPs</h2>
        <div class="grid">
          <label>Search saved UPs <input id="up-search" placeholder="Name or UID"></label>
          <div id="ups" class="up-list"></div>
        </div>
      </section>
    </div>
    <div class="work">
      <section class="selection-card">
        <h2>Selection</h2>
        <div class="grid">
          <label>Selection mode
            <select id="selection-kind">
              <option value="position">Published-time number range</option>
              <option value="published">Published time range</option>
              <option value="metric">Metric value range</option>
            </select>
          </label>
          <div id="selection-position" class="row">
            <label>Start number <input id="position-start" value="1"></label>
            <label>End number <input id="position-end" value="20"></label>
          </div>
          <div id="selection-published" class="row" hidden>
            <label>Start time <input id="published-start" placeholder="2026-01-01"></label>
            <label>End time <input id="published-end" placeholder="2026-06-05"></label>
          </div>
          <div id="selection-metric" class="row" hidden>
            <label>Metric <select id="metric-field"></select></label>
            <label>Greater than <input id="metric-min" placeholder="100k"></label>
            <label>Less than <input id="metric-max" placeholder="200k"></label>
          </div>
        </div>
        <div id="progress" class="progress">Idle.</div>
      </section>
      <section id="panel-up" class="panel active">
        <h2>Selected UP Detail</h2>
        <button id="load-up-detail">View Selected UP Detail</button>
        <div id="up-detail-result" class="detail-box"></div>
      </section>
      <section id="panel-videos" class="panel">
        <h2>Videos</h2>
        <p class="muted">List selected videos ordered by published time.</p>
        <button id="list-videos">List Videos</button>
        <div id="videos-result" class="result"></div>
      </section>
      <section id="panel-analysis" class="panel">
        <h2>Analysis</h2>
        <p class="muted">Calculate mean and median for selected videos.</p>
        <button id="run-analysis">Calculate Mean and Median</button>
        <div id="analysis-result" class="result"></div>
      </section>
      <section id="panel-division" class="panel">
        <h2>Division</h2>
        <div class="row">
          <label>Mode
            <select id="division-mode">
              <option value="single">Ratio for every selected video</option>
              <option value="aggregate">One ratio for all selected videos</option>
            </select>
          </label>
          <label>Numerator <select id="division-numerator"></select></label>
          <label>Denominator <select id="division-denominator"></select></label>
        </div>
        <button id="run-division">Calculate Division</button>
        <div id="division-result" class="result"></div>
      </section>
      <section id="panel-plot" class="panel">
        <h2>Plot</h2>
        <div class="row">
          <label>Plot mode
            <select id="plot-mode">
              <option value="field">One video metric</option>
              <option value="quotient">Quotient</option>
            </select>
          </label>
          <label class="plot-field-control">Video metric <select id="plot-field"></select></label>
          <label class="plot-quotient-control" hidden>Numerator <select id="plot-numerator"></select></label>
          <label class="plot-quotient-control" hidden>Denominator <select id="plot-denominator"></select></label>
        </div>
        <button id="run-plot">Plot Selected Videos</button>
        <div id="plot-progress" class="progress panel-progress" hidden>Idle.</div>
        <div id="plot-chart" class="chart"></div>
        <div id="plot-result" class="result"></div>
      </section>
      <section id="panel-saved-plots" class="panel">
        <h2>Saved Plot PNGs</h2>
        <div id="plots"></div>
      </section>
      <section id="panel-settings" class="panel">
        <h2>Settings</h2>
        <div class="row">
          <button id="start-qr">Start QR Sign In</button>
          <button id="check-qr">Check QR Status</button>
          <button id="load-account">View Account Detail</button>
          <button id="use-guest">Use Guest Mode</button>
          <button id="sign-out-keep">Sign Out, Keep Cache</button>
          <button id="sign-out-selected">Remove Selected Cache</button>
          <button id="sign-out-all">Remove All Caches</button>
        </div>
        <div class="row">
          <label>Request frequency <input id="request-frequency" value="4"></label>
          <button id="set-frequency">Set Frequency</button>
        </div>
        <div id="qr-result" class="result"></div>
        <h3>Cached Accounts</h3>
        <div id="accounts-result" class="result"></div>
        <h3>Account Detail</h3>
        <div id="account-result" class="detail-box"></div>
      </section>
    </div>
  </main>
  <script>
    const metricFields = [
      ["views", "Views"],
      ["likes", "Likes"],
      ["replies", "Replies"],
      ["favorites", "Favorites"],
      ["coins", "Coins"],
      ["shares", "Shares"]
    ];
    const divisionFields = [...metricFields, ["followers", "Followers"]];
    let savedUPs = [];
    let selectedUP = null;

    async function getJSON(url) {
      const response = await fetch(url);
      if (!response.ok) throw new Error(await response.text());
      return response.json();
    }
    async function postJSON(url, data) {
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data)
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || JSON.stringify(result));
      return result;
    }

    function formatBytes(value) {
      if (value < 1024) return `${value} B`;
      if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
      return `${(value / 1024 / 1024).toFixed(1)} MB`;
    }

    function escapeHTML(value) {
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }

    async function selectUP(uid) {
      await postJSON("/api/selected-up", { uid });
      await load();
    }
    function fillOptions(id, fields) {
      document.getElementById(id).innerHTML = fields
        .map(([value, label]) => `<option value="${value}">${label}</option>`)
        .join("");
    }
    function selectionPayload() {
      const kind = document.getElementById("selection-kind").value;
      if (kind === "position") {
        return {
          kind,
          start: document.getElementById("position-start").value,
          end: document.getElementById("position-end").value
        };
      }
      if (kind === "published") {
        return {
          kind,
          start_time: document.getElementById("published-start").value,
          end_time: document.getElementById("published-end").value
        };
      }
      return {
        kind,
        metric: document.getElementById("metric-field").value,
        minimum: document.getElementById("metric-min").value,
        maximum: document.getElementById("metric-max").value
      };
    }
    function table(headers, rows, rawLastColumn = false) {
      return `<table><thead><tr>${headers.map((h) => `<th>${escapeHTML(h)}</th>`).join("")}</tr></thead><tbody>${
        rows.map((row) => `<tr>${row.map((value, index) => {
          if (rawLastColumn && index === row.length - 1) return `<td>${value}</td>`;
          return `<td>${escapeHTML(value ?? "Unknown")}</td>`;
        }).join("")}</tr>`).join("")
      }</tbody></table>`;
    }
    function formatValue(value) {
      if (value === null || value === undefined || value === "") return "Unknown";
      if (typeof value === "boolean") return value ? "Yes" : "No";
      if (typeof value === "number") return value.toLocaleString();
      return String(value);
    }
    function renderDetailRows(target, rows) {
      document.getElementById(target).innerHTML = table(
        ["Field", "Value"],
        rows.map(([label, value]) => [label, formatValue(value)])
      );
    }
    function renderAccountDetail(detail) {
      renderDetailRows("account-result", [
        ["Name", detail.name || detail.uname],
        ["UID", detail.mid || detail.uid],
        ["Level", detail.level],
        ["Coins", detail.coins],
        ["Following", detail.following],
        ["Followers", detail.follower],
        ["VIP type", detail.vip && detail.vip.type],
        ["VIP status", detail.vip && detail.vip.status],
        ["Signature", detail.sign]
      ]);
    }
    function renderUPDetail(detail) {
      const selected = detail.selected || {};
      const profile = detail.profile || {};
      const relation = detail.relation || {};
      const official = profile.official || {};
      const upStat = profile.upstat || {};
      renderDetailRows("up-detail-result", [
        ["Name", profile.name || selected.name],
        ["UID", profile.mid || selected.uid],
        ["Signature", profile.sign || "None"],
        ["Official title", official.title],
        ["Official description", official.desc],
        ["Followers", relation.follower],
        ["Following", relation.following],
        ["Released videos", detail.video_total],
        ["Total video views", upStat.archive && upStat.archive.view],
        ["Total likes", upStat.likes]
      ]);
    }
    function renderVideos(target, videos) {
      document.getElementById(target).innerHTML = table(
        ["Title", "Published", "Views", "Likes", "Replies", "Favorites", "Coins", "Shares", "BVID"],
        videos.map((item) => [item.title, item.published_time, item.views, item.likes, item.replies, item.favorites, item.coins, item.shares, item.bvid])
      );
    }
    function renderSavedUPs() {
      const query = document.getElementById("up-search").value.trim().toLowerCase();
      const filtered = savedUPs.filter((up) => {
        const name = String(up.name || "").toLowerCase();
        const uid = String(up.uid || "").toLowerCase();
        return !query || name.includes(query) || uid.includes(query);
      });
      document.getElementById("ups").innerHTML = filtered.map((up) => `
        <div class="up ${selectedUP && selectedUP.uid === up.uid ? "active" : ""}">
          <strong>${escapeHTML(up.name)}</strong>
          <span class="muted">UID ${escapeHTML(up.uid)}</span>
          <button type="button" data-uid="${escapeHTML(up.uid)}">Select</button>
        </div>
      `).join("") || `<p class="muted">No saved UPs match this search.</p>`;
      document.querySelectorAll("button[data-uid]").forEach((button) => {
        button.addEventListener("click", () => selectUP(button.dataset.uid));
      });
    }
    function updatePlotControls() {
      const quotient = document.getElementById("plot-mode").value === "quotient";
      document.querySelectorAll(".plot-field-control").forEach((element) => {
        element.hidden = quotient;
      });
      document.querySelectorAll(".plot-quotient-control").forEach((element) => {
        element.hidden = !quotient;
      });
    }
    function formatAxisNumber(value) {
      const number = Number(value);
      if (!Number.isFinite(number)) return "0";
      const abs = Math.abs(number);
      if (abs >= 1000000) {
        return new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 2 }).format(number);
      }
      if (abs >= 1000) {
        return new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(number);
      }
      if (abs >= 1) {
        return new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(number);
      }
      if (abs >= 0.01) {
        return new Intl.NumberFormat(undefined, { maximumFractionDigits: 4 }).format(number);
      }
      if (number === 0) return "0";
      return number.toExponential(2);
    }
    function renderPlot(points, yLabel = "Value") {
      const host = document.getElementById("plot-chart");
      const plotPoints = points
        .map((point) => ({ ...point, value: Number(point.value) }))
        .filter((point) => Number.isFinite(point.value));
      if (!plotPoints.length) {
        host.innerHTML = "<p class='muted'>No points to plot.</p>";
        return;
      }
      const width = 1040;
      const height = 430;
      const padding = { top: 30, right: 28, bottom: 78, left: 96 };
      const plotWidth = width - padding.left - padding.right;
      const plotHeight = height - padding.top - padding.bottom;
      const values = plotPoints.map((point) => point.value);
      let min = Math.min(...values);
      let max = Math.max(...values);
      const spread = max - min;
      const pad = spread ? Math.max(spread * 0.12, Math.abs(max) * 0.03, 1) : Math.max(Math.abs(max) * 0.12, 1);
      min -= pad;
      max += pad;
      const domain = max - min || 1;
      const step = plotPoints.length > 1 ? plotWidth / (plotPoints.length - 1) : 0;
      const coords = plotPoints.map((point, index) => {
        const x = padding.left + step * index;
        const y = padding.top + plotHeight - ((point.value - min) / domain) * plotHeight;
        return { x, y, point };
      });
      const line = coords.map((coord) => `${coord.x},${coord.y}`).join(" ");
      const tickCount = 6;
      const yTicks = Array.from({ length: tickCount }, (_, index) => min + (domain * index) / (tickCount - 1));
      const xTickStep = Math.max(1, Math.ceil(plotPoints.length / 7));
      const xTicks = plotPoints
        .map((point, index) => ({ point, index }))
        .filter(({ index }) => index === 0 || index === plotPoints.length - 1 || index % xTickStep === 0);
      host.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img">
        <rect x="0" y="0" width="${width}" height="${height}" fill="#fff"/>
        ${yTicks.map((tick) => {
          const y = padding.top + plotHeight - ((tick - min) / domain) * plotHeight;
          return `<line x1="${padding.left}" y1="${y}" x2="${width - padding.right}" y2="${y}" stroke="#e5e5e5"/>
            <text x="${padding.left - 10}" y="${y + 4}" text-anchor="end" fill="#555" font-size="13">${escapeHTML(formatAxisNumber(tick))}</text>`;
        }).join("")}
        <line x1="${padding.left}" y1="${padding.top + plotHeight}" x2="${width - padding.right}" y2="${padding.top + plotHeight}" stroke="#111" stroke-width="1.5"/>
        <line x1="${padding.left}" y1="${padding.top}" x2="${padding.left}" y2="${padding.top + plotHeight}" stroke="#111" stroke-width="1.5"/>
        ${xTicks.map(({ point, index }) => {
          const x = padding.left + step * index;
          const label = String(point.label || "").slice(0, 10);
          return `<line x1="${x}" y1="${padding.top + plotHeight}" x2="${x}" y2="${padding.top + plotHeight + 6}" stroke="#111"/>
            <text x="${x}" y="${padding.top + plotHeight + 24}" text-anchor="middle" fill="#555" font-size="12">${escapeHTML(label)}</text>`;
        }).join("")}
        <polyline points="${line}" fill="none" stroke="#111" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>
        ${coords.map((coord) => `<circle cx="${coord.x}" cy="${coord.y}" r="4.5" fill="#111"><title>${escapeHTML(coord.point.title)} | ${escapeHTML(coord.point.label)} | ${escapeHTML(formatAxisNumber(coord.point.value))}</title></circle>`).join("")}
        <text x="${padding.left + plotWidth / 2}" y="${height - 18}" text-anchor="middle" fill="#111" font-size="14">Published time</text>
        <text transform="translate(24 ${padding.top + plotHeight / 2}) rotate(-90)" text-anchor="middle" fill="#111" font-size="14">${escapeHTML(yLabel)}</text>
      </svg>`;
    }
    let progressTimer = null;
    let progressStartedAt = null;
    let activeProgressTarget = null;
    function progressLine(data) {
      const elapsed = progressStartedAt ? ` Elapsed: ${Math.max(0, Math.round((Date.now() - progressStartedAt) / 1000))}s.` : "";
      const count = data.count === null || data.count === undefined ? "" : ` Selected: ${data.count}.`;
      return `${data.message || "Running."}${elapsed}${count}`;
    }
    function setProgressText(line) {
      document.getElementById("progress").textContent = line;
      if (activeProgressTarget) {
        const target = document.getElementById(activeProgressTarget);
        if (target) {
          target.hidden = false;
          target.textContent = line;
        }
      }
    }
    async function refreshProgress() {
      const data = await getJSON("/api/progress");
      setProgressText(progressLine(data));
      return data;
    }
    function startProgressPolling(label, targetId = null) {
      clearInterval(progressTimer);
      progressStartedAt = Date.now();
      activeProgressTarget = targetId;
      setProgressText(`${label}: request started.`);
      progressTimer = setInterval(() => {
        refreshProgress().catch(() => {});
      }, 800);
    }
    async function stopProgressPolling() {
      clearInterval(progressTimer);
      progressTimer = null;
      await refreshProgress().catch(() => {});
      progressStartedAt = null;
      activeProgressTarget = null;
    }
    async function runAction(action, extra = {}, progressTarget = null) {
      const labels = { list: "Listing videos", analysis: "Analyzing videos", division: "Calculating division", plot: "Plotting data" };
      startProgressPolling(labels[action] || "Running action", progressTarget);
      try {
        return await postJSON("/api/video-action", { action, selection: selectionPayload(), ...extra });
      } finally {
        await stopProgressPolling();
      }
    }

    async function load() {
      const [health, ups, plots, accounts] = await Promise.all([
        getJSON("/api/health"),
        getJSON("/api/ups"),
        getJSON("/api/plots"),
        getJSON("/api/accounts")
      ]);

      document.getElementById("status").textContent =
        `Server running. Account: ${health.account}. Request frequency: ${health.request_frequency} request(s)/second.`;

      const selected = health.selected_up;
      selectedUP = selected;
      savedUPs = ups.ups;
      document.getElementById("selected").textContent = selected
        ? `${selected.name} (UID ${selected.uid})`
        : "No UP selected.";

      renderSavedUPs();

      document.getElementById("plots").innerHTML = `<div class="saved-plots-grid">${plots.plots.map((plot) => `
        <article class="saved-plot">
          <a href="${escapeHTML(plot.url)}" target="_blank" rel="noreferrer"><img src="${escapeHTML(plot.url)}" alt="${escapeHTML(plot.name)}"></a>
          <footer>
            <span>${escapeHTML(plot.name)}</span>
            <span>${formatBytes(plot.size)}</span>
          </footer>
        </article>
      `).join("") || `<p class="muted">No plots generated yet.</p>`}</div>`;
      document.getElementById("accounts-result").innerHTML = table(
        ["Name", "UID", "Source", "Active", "Action"],
        accounts.accounts.map((account) => [
          account.name,
          account.uid,
          account.source,
          account.active ? "Yes" : "No",
          `<button type="button" data-account="${escapeHTML(account.id)}">Select</button>`
        ]),
        true
      );
      document.querySelectorAll("button[data-account]").forEach((button) => {
        button.addEventListener("click", async () => {
          await postJSON("/api/account/select", { id: button.dataset.account });
          await load();
        });
      });
    }

    function setup() {
      ["metric-field", "plot-field"].forEach((id) => fillOptions(id, metricFields));
      ["division-numerator", "division-denominator", "plot-numerator", "plot-denominator"].forEach((id) => fillOptions(id, divisionFields));
      document.querySelectorAll("button[data-panel]").forEach((button) => {
        button.addEventListener("click", () => {
          document.querySelectorAll(".panel").forEach((panel) => panel.classList.remove("active"));
          document.getElementById(`panel-${button.dataset.panel}`).classList.add("active");
          document.querySelector(".selection-card").hidden = button.dataset.panel === "settings";
          document.querySelectorAll("button[data-panel]").forEach((navButton) => navButton.removeAttribute("aria-current"));
          button.setAttribute("aria-current", "page");
        });
      });
      document.getElementById("up-search").addEventListener("input", renderSavedUPs);
      document.getElementById("plot-mode").addEventListener("change", updatePlotControls);
      updatePlotControls();
      document.getElementById("selection-kind").addEventListener("change", (event) => {
        document.getElementById("selection-position").hidden = event.target.value !== "position";
        document.getElementById("selection-published").hidden = event.target.value !== "published";
        document.getElementById("selection-metric").hidden = event.target.value !== "metric";
      });
      document.getElementById("add-up").addEventListener("click", async () => {
        await postJSON("/api/ups/add", {
          name: document.getElementById("new-up-name").value,
          space: document.getElementById("new-up-space").value
        });
        await load();
      });
      document.getElementById("list-videos").addEventListener("click", async () => {
        const data = await runAction("list");
        renderVideos("videos-result", data.videos);
      });
      document.getElementById("run-analysis").addEventListener("click", async () => {
        const data = await runAction("analysis");
        document.getElementById("analysis-result").innerHTML = table(
          ["Metric", "Count", "Mean", "Median"],
          data.summaries.map((item) => [item.label, item.count, item.mean, item.median])
        );
      });
      document.getElementById("run-division").addEventListener("click", async () => {
        const data = await runAction("division", {
          mode: document.getElementById("division-mode").value,
          numerator: document.getElementById("division-numerator").value,
          denominator: document.getElementById("division-denominator").value
        });
        if (data.mode === "aggregate") {
          document.getElementById("division-result").innerHTML = table(["Numerator", "Denominator", "Ratio"], [[data.numerator_total, data.denominator_total, data.ratio]]);
        } else {
          document.getElementById("division-result").innerHTML = table(
            ["Title", "Published", "Numerator", "Denominator", "Ratio"],
            data.rows.map((row) => [row.title, row.published_time, row.numerator, row.denominator, row.ratio])
          );
        }
      });
      document.getElementById("run-plot").addEventListener("click", async () => {
        const data = await runAction("plot", {
          plot_mode: document.getElementById("plot-mode").value,
          field: document.getElementById("plot-field").value,
          numerator: document.getElementById("plot-numerator").value,
          denominator: document.getElementById("plot-denominator").value
        }, "plot-progress");
        renderPlot(data.points, data.y_label || data.plot_label || "Value");
        const savedPlot = data.plot_file ? `<p class="muted">Saved PNG: ${escapeHTML(data.plot_file)}</p>` : "";
        document.getElementById("plot-result").innerHTML = savedPlot + table(["Title", "Published", "Value"], data.points.map((point) => [point.title, point.label, point.value]));
        await load();
      });
      document.getElementById("load-account").addEventListener("click", async () => {
        renderAccountDetail(await getJSON("/api/account-detail"));
      });
      document.getElementById("use-guest").addEventListener("click", async () => {
        await postJSON("/api/sign-out", { mode: "keep" });
        await load();
      });
      document.getElementById("sign-out-keep").addEventListener("click", async () => {
        await postJSON("/api/sign-out", { mode: "keep" });
        await load();
      });
      document.getElementById("sign-out-selected").addEventListener("click", async () => {
        await postJSON("/api/sign-out", { mode: "selected" });
        await load();
      });
      document.getElementById("sign-out-all").addEventListener("click", async () => {
        await postJSON("/api/sign-out", { mode: "all" });
        await load();
      });
      document.getElementById("set-frequency").addEventListener("click", async () => {
        await postJSON("/api/request-frequency", { value: document.getElementById("request-frequency").value });
        await load();
      });
      document.getElementById("start-qr").addEventListener("click", async () => {
        const data = await postJSON("/api/sign-in/qr/start", {});
        document.getElementById("qr-result").innerHTML = `<p class="muted">Scan this QR code with the Bilibili app, then click Check QR Status.</p><img src="${data.qr_code_url}?t=${Date.now()}" alt="Bilibili sign-in QR code">`;
      });
      document.getElementById("check-qr").addEventListener("click", async () => {
        const data = await postJSON("/api/sign-in/qr/status", {});
        document.getElementById("qr-result").innerHTML = table(["Field", "Value"], Object.entries(data).map(([key, value]) => [key, typeof value === "object" ? JSON.stringify(value) : value]));
        await load();
      });
      document.getElementById("load-up-detail").addEventListener("click", async () => {
        renderUPDetail(await getJSON("/api/up-detail"));
      });
    }
    setup();
    load().catch((error) => {
      document.getElementById("status").textContent = error.message;
    });
  </script>
</body>
</html>
""".encode("utf-8")


class BilibiliDataScienceHandler(BaseHTTPRequestHandler):
    server_version = "BilibiliDataScienceWeb/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}")

    def send_bytes(
        self,
        body: bytes,
        content_type: str,
        status: HTTPStatus = HTTPStatus.OK,
        *,
        send_body: bool = True,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if send_body:
            self.wfile.write(body)

    def send_json(self, data: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_bytes(json_bytes(data), "application/json; charset=utf-8", status)

    def send_error_json(self, status: HTTPStatus, message: str) -> None:
        self.send_json({"error": message}, status)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            self.send_bytes(dashboard_html(), "text/html; charset=utf-8")
            return
        if path == "/api/health":
            self.send_json(
                {
                    "ok": True,
                    "selected_up": selected_up(),
                    "account": account_summary(),
                    "request_frequency": REQUEST_FREQUENCY,
                }
            )
            return
        if path == "/api/ups":
            self.send_json({"ups": load_web_ups(), "selected_up": selected_up()})
            return
        if path == "/api/plots":
            self.send_json({"plots": plot_entries()})
            return
        if path == "/api/progress":
            self.send_json(PROGRESS)
            return
        if path == "/api/accounts":
            self.send_json({"accounts": account_records_summary()})
            return
        if path == "/api/account-detail":
            try:
                self.send_json(asyncio.run(account_detail()))
            except Exception as exc:
                self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            return
        if path == "/api/up-detail":
            try:
                self.send_json(asyncio.run(selected_up_detail()))
            except Exception as exc:
                self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            return
        if path == "/favicon.ico":
            self.send_bytes(b"", "image/x-icon", HTTPStatus.NO_CONTENT)
            return
        if path == "/runtime/qrcode.png":
            self.serve_qrcode()
            return
        if path.startswith("/plots/"):
            self.serve_plot(path.removeprefix("/plots/"))
            return

        self.send_error_json(HTTPStatus.NOT_FOUND, "Not found.")

    def do_HEAD(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            self.send_bytes(dashboard_html(), "text/html; charset=utf-8", send_body=False)
            return
        if path == "/api/health":
            self.send_bytes(b"{}", "application/json; charset=utf-8", send_body=False)
            return
        if path == "/api/ups":
            self.send_bytes(b"{}", "application/json; charset=utf-8", send_body=False)
            return
        if path == "/api/plots":
            self.send_bytes(b"{}", "application/json; charset=utf-8", send_body=False)
            return
        if path == "/api/progress":
            self.send_bytes(b"{}", "application/json; charset=utf-8", send_body=False)
            return
        if path == "/api/accounts":
            self.send_bytes(b"{}", "application/json; charset=utf-8", send_body=False)
            return
        if path in {"/api/account-detail", "/api/up-detail"}:
            self.send_bytes(b"{}", "application/json; charset=utf-8", send_body=False)
            return
        if path == "/favicon.ico":
            self.send_bytes(b"", "image/x-icon", HTTPStatus.NO_CONTENT, send_body=False)
            return
        if path == "/runtime/qrcode.png":
            self.send_bytes(b"", "image/png", send_body=False)
            return
        if path.startswith("/plots/"):
            name = Path(unquote(path.removeprefix("/plots/"))).name
            plot_path = PLOTS_DIR / name
            if plot_path.is_file() and plot_path.suffix.lower() == ".png":
                content_type = mimetypes.guess_type(plot_path.name)[0] or "application/octet-stream"
                self.send_bytes(b"", content_type, send_body=False)
                return

        self.send_bytes(b"", "application/json; charset=utf-8", HTTPStatus.NOT_FOUND, send_body=False)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path not in {
            "/api/selected-up",
            "/api/ups/add",
            "/api/video-action",
            "/api/request-frequency",
            "/api/sign-out",
            "/api/account/select",
            "/api/sign-in/qr/start",
            "/api/sign-in/qr/status",
        }:
            self.send_error_json(HTTPStatus.NOT_FOUND, "Not found.")
            return

        try:
            data = read_json_body(self)
        except ValueError as exc:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            return

        try:
            if path == "/api/selected-up":
                uid = str(data.get("uid") or "").strip()
                if not uid:
                    raise ValueError("uid is required.")
                entry = select_up_by_uid(uid)
                if entry is None:
                    self.send_error_json(HTTPStatus.NOT_FOUND, "UP was not found.")
                    return
                self.send_json({"selected_up": entry})
                return
            if path == "/api/ups/add":
                entry = add_web_up(str(data.get("name") or "").strip(), str(data.get("space") or "").strip())
                self.send_json({"up": entry})
                return
            if path == "/api/video-action":
                self.send_json(asyncio.run(execute_video_action(data)))
                return
            if path == "/api/request-frequency":
                global REQUEST_FREQUENCY
                value = float(data.get("value"))
                if value <= 0:
                    raise ValueError("Request frequency must be greater than 0.")
                REQUEST_FREQUENCY = value
                APP.REQUEST_FREQUENCY = value
                self.send_json({"request_frequency": REQUEST_FREQUENCY})
                return
            if path == "/api/sign-out":
                self.send_json(sign_out_web(str(data.get("mode") or "keep")))
                return
            if path == "/api/account/select":
                self.send_json({"account": select_account(str(data.get("id") or ""))})
                return
            if path == "/api/sign-in/qr/start":
                self.send_json(asyncio.run(start_qr_sign_in()))
                return
            if path == "/api/sign-in/qr/status":
                self.send_json(asyncio.run(qr_sign_in_status()))
                return
        except Exception as exc:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))

    def serve_plot(self, raw_name: str) -> None:
        name = Path(unquote(raw_name)).name
        path = PLOTS_DIR / name
        try:
            resolved = path.resolve()
            plots_root = PLOTS_DIR.resolve()
        except OSError:
            self.send_error_json(HTTPStatus.NOT_FOUND, "Plot was not found.")
            return

        if plots_root not in resolved.parents or not resolved.is_file() or resolved.suffix.lower() != ".png":
            self.send_error_json(HTTPStatus.NOT_FOUND, "Plot was not found.")
            return

        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_bytes(resolved.read_bytes(), content_type)

    def serve_qrcode(self) -> None:
        path = APP.QRCODE_FILE
        if not path.is_file():
            self.send_error_json(HTTPStatus.NOT_FOUND, "QR code is not available.")
            return
        self.send_bytes(path.read_bytes(), "image/png")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local Bilibili Data Science web server.")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind. Default: 127.0.0.1")
    parser.add_argument("--port", default=8000, type=int, help="Port to bind. Default: 8000")
    parser.add_argument(
        "--port-retries",
        default=10,
        type=int,
        help="Number of following ports to try if the requested port is busy. Default: 10",
    )
    parser.add_argument(
        "--open-browser",
        action="store_true",
        help="Open the web UI in the default browser after the server starts.",
    )
    parser.add_argument(
        "--browser",
        default="chrome",
        choices=["chrome", "default", "none"],
        help="Browser opener to use with --open-browser. Default: chrome",
    )
    return parser.parse_args()


def create_server(host: str, start_port: int, retries: int) -> tuple[ThreadingHTTPServer, int]:
    last_error: OSError | None = None
    for port in range(start_port, start_port + max(retries, 0) + 1):
        try:
            return ThreadingHTTPServer((host, port), BilibiliDataScienceHandler), port
        except OSError as exc:
            last_error = exc
            if exc.errno not in (48, 98, 10048):
                raise
            print(f"Port {port} is already in use.")
            continue
    raise OSError(f"Could not bind {host}:{start_port}-{start_port + retries}") from last_error


def open_browser(url: str, browser_name: str) -> None:
    if browser_name == "none":
        return
    if browser_name == "chrome":
        try:
            subprocess.run(["open", "-a", "Google Chrome", url], check=False)
            return
        except OSError as exc:
            print(f"Could not open Google Chrome directly: {exc}")
    webbrowser.open(url)


def main() -> None:
    args = parse_args()
    server, port = create_server(args.host, args.port, args.port_retries)
    url = f"http://{args.host}:{port}"
    print(f"Serving Bilibili Data Science web UI at {url}")
    if args.open_browser:
        open_browser(url, args.browser)
    print("Press Ctrl+C to stop the server.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping web server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
