"""Bilibili video and creator data retrieval."""

import asyncio
from datetime import datetime
from typing import Any

from bilibili_api import Credential, user, video

from bilibili_ds.accounts import (
    credential_for_requests,
)
from bilibili_ds.client import (
    close_bilibili_client,
    configure_bilibili_client,
    request_delay_seconds,
)
from bilibili_ds.storage import (
    load_selected_up,
    uid_from_up,
)


def first_video(videos: dict[str, Any]) -> dict[str, Any]:
    items = videos.get("list", {}).get("vlist", [])
    if not items:
        raise LookupError("No video found for the user.")
    return items[0]


async def fetch_latest_video_like(uid: int, credential: Credential | None) -> dict[str, Any]:
    uploader = user.User(uid, credential=credential)

    videos = await uploader.get_videos(pn=1, ps=1, order=user.VideoOrder.PUBDATE)
    item = first_video(videos)
    await asyncio.sleep(request_delay_seconds())

    info = await video.Video(bvid=item["bvid"], credential=credential).get_info()
    stat = info.get("stat", {})
    return {
        "title": info.get("title") or item.get("title"),
        "bvid": info.get("bvid") or item.get("bvid"),
        "aid": info.get("aid") or item.get("aid"),
        "pubdate": datetime.fromtimestamp(info["pubdate"]).isoformat(sep=" ") if info.get("pubdate") else None,
        "like": stat.get("like"),
        "view": stat.get("view"),
        "reply": stat.get("reply"),
        "favorite": stat.get("favorite"),
        "coin": stat.get("coin"),
        "share": stat.get("share"),
    }


def video_total_from_response(videos: dict[str, Any]) -> int:
    page = videos.get("page", {})
    for key in ("count", "total"):
        try:
            return int(page[key])
        except (KeyError, TypeError, ValueError):
            continue
    return len(videos.get("list", {}).get("vlist", []))


async def fetch_video_summaries(
    uploader: Any,
    target_count: int,
    order: user.VideoOrder,
) -> list[dict[str, Any]]:
    page_size = 30
    fetched_items: list[dict[str, Any]] = []
    page_number = 1

    while len(fetched_items) < target_count:
        try:
            page_data = await uploader.get_videos(pn=page_number, ps=page_size, order=order)
        except Exception as exc:
            print(f"Failed to fetch video page {page_number}: {exc}")
            break

        page_items = page_data.get("list", {}).get("vlist", [])
        if not page_items:
            break

        fetched_items.extend(page_items[: target_count - len(fetched_items)])
        page_number += 1
        await asyncio.sleep(request_delay_seconds())

    return fetched_items


async def fetch_video_detail(item: dict[str, Any], credential: Credential | None) -> dict[str, Any]:
    enriched = dict(item)
    bvid = enriched.get("bvid")
    if not bvid:
        enriched["stat"] = {}
        enriched["detail_error"] = "No BVID available."
        return enriched

    try:
        info = await video.Video(bvid=bvid, credential=credential).get_info()
    except Exception as exc:
        enriched["stat"] = {}
        enriched["detail_error"] = str(exc)
        return enriched

    stat = info.get("stat") if isinstance(info.get("stat"), dict) else {}
    enriched.update(
        {
            "title": info.get("title") or enriched.get("title"),
            "bvid": info.get("bvid") or enriched.get("bvid"),
            "aid": info.get("aid") or enriched.get("aid"),
            "pubdate": info.get("pubdate") or enriched.get("pubdate") or enriched.get("created"),
            "stat": stat,
        }
    )
    return enriched


async def fetch_selected_up_details() -> tuple[dict[str, Any] | None, str | None]:
    selected_up = load_selected_up()
    if selected_up is None:
        return None, "No UP is selected."

    uid = uid_from_up(selected_up)
    credential = credential_for_requests()
    uploader = user.User(uid, credential=credential)

    configure_bilibili_client()
    try:
        info = await uploader.get_user_info()
        relation = await uploader.get_relation_info()
        first_page = await uploader.get_videos(pn=1, ps=1, order=user.VideoOrder.PUBDATE)
        details: dict[str, Any] = {
            "selected": selected_up,
            "profile": info,
            "relation": relation,
            "video_total": video_total_from_response(first_page),
            "fetched_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
        }

        if credential is not None and credential.has_bili_jct():
            try:
                details["up_stat"] = await uploader.get_up_stat()
            except Exception as exc:
                details["up_stat_error"] = str(exc)
        return details, None
    except Exception as exc:
        return None, str(exc)
    finally:
        await close_bilibili_client()
