"""Browser video fetching, selection, and progress updates."""

from __future__ import annotations

import asyncio
from typing import Any

from bilibili_api import user, video

from bilibili_ds import accounts as account_service, client, selection as video_selection, videos as video_service
from bilibili_ds.web.creators import selected_up
from bilibili_ds.web.progress import set_progress
from bilibili_ds.web.serializers import (
    extract_bvid,
    field_by_name,
    int_or_none,
    parse_range_number,
    serialize_single_video,
    sort_by_published_time,
    video_metric,
    video_timestamp,
)


async def fetch_single_video(value: Any) -> dict[str, Any]:
    try:
        bvid = extract_bvid(value)
    except ValueError as exc:
        set_progress(f"Lookup failed: {exc}", running=False, percent=100, count=0)
        raise
    credential = account_service.credential_from_env()
    client.configure_bilibili_client()
    set_progress(f"Looking up {bvid}.", running=True, percent=15, count=0)
    try:
        info = await video.Video(bvid=bvid, credential=credential).get_info()
        if not isinstance(info, dict) or not info:
            raise ValueError("Bilibili returned no video information.")
        set_progress(f"Lookup completed for {bvid}.", running=False, percent=100, count=1)
        return serialize_single_video(info)
    except Exception as exc:
        set_progress(f"Lookup failed for {bvid}: {exc}", running=False, percent=100, count=0)
        raise ValueError(
            f"Could not fetch {bvid}. The video may be unavailable or private, or Bilibili may have rejected the request. {exc}"
        ) from exc
    finally:
        await client.close_bilibili_client()


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
        await asyncio.sleep(client.request_delay_seconds())

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
        enriched_items.append(await video_service.fetch_video_detail(item, credential))
        set_progress(
            f"{progress_label}: fetched detail {index}/{total}.",
            percent=start_percent + int((index / total) * (end_percent - start_percent)),
            count=index,
        )
        await asyncio.sleep(client.request_delay_seconds())

    return enriched_items


async def fetch_selected_video_items(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], str, int | None]:
    selected = selected_up()
    if selected is None:
        raise ValueError("No UP is selected.")

    credential = account_service.credential_from_env()
    uploader = user.User(int(selected["uid"]), credential=credential)
    selection = payload.get("selection") if isinstance(payload.get("selection"), dict) else {}
    kind = selection.get("kind") or "latest"
    action = str(payload.get("action") or "video")
    action_label = {"list": "Listing", "analysis": "Analysis", "division": "Division", "plot": "Plotting"}.get(action, "Video action")

    client.configure_bilibili_client()
    try:
        set_progress(f"{action_label}: checking selected UP video count.", running=True, percent=5, count=0)
        first_page = await uploader.get_videos(pn=1, ps=1, order=user.VideoOrder.PUBDATE)
        total = video_service.video_total_from_response(first_page)
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
                user.VideoOrder.PUBDATE,
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
            user.VideoOrder.PUBDATE,
            progress_label=f"{action_label}: fetching summaries for all {total} video(s)",
            start_percent=15,
            end_percent=50,
        )

        if kind == "published":
            start_raw = str(selection.get("start_time") or "").strip()
            end_raw = str(selection.get("end_time") or "").strip()
            if not start_raw or not end_raw:
                raise ValueError("Start time and end time are required.")
            start_dt = video_selection.parse_datetime_input(start_raw)
            end_dt = video_selection.parse_datetime_input(end_raw, end_of_day=True)
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
        await client.close_bilibili_client()


async def fetch_followers() -> int | None:
    selected = selected_up()
    if selected is None:
        return None
    credential = account_service.credential_from_env()
    uploader = user.User(int(selected["uid"]), credential=credential)
    client.configure_bilibili_client()
    try:
        relation = await uploader.get_relation_info()
        return int_or_none(relation.get("follower"))
    finally:
        await client.close_bilibili_client()


async def selected_up_detail() -> dict[str, Any]:
    selected = selected_up()
    if selected is None:
        raise ValueError("No UP is selected.")
    credential = account_service.credential_from_env()
    uploader = user.User(int(selected["uid"]), credential=credential)
    client.configure_bilibili_client()
    try:
        info = await uploader.get_user_info()
        relation = await uploader.get_relation_info()
        first_page = await uploader.get_videos(pn=1, ps=1, order=user.VideoOrder.PUBDATE)
        return {
            "selected": selected,
            "profile": info,
            "relation": relation,
            "video_total": video_service.video_total_from_response(first_page),
        }
    finally:
        await client.close_bilibili_client()
