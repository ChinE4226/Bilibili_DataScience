"""Video response handling and detail fetching used by the website."""

from typing import Any

import httpx
from bilibili_api import Credential, video
from bilibili_api.exceptions import WbiRetryTimesExceedException


async def fetch_creator_video_page(uploader, *, pn, ps, order, collected=None,
                                  requested=None, item_kind='valid videos'):
    """Keep useful failure details without exposing the SDK's raw response."""
    try:
        return await uploader.get_videos(pn=pn, ps=ps, order=order)
    except Exception as exc:
        code, status = getattr(exc, 'code', None), getattr(exc, 'status', None)
        if not isinstance(code, int) or isinstance(code, bool):
            code = None
        if not isinstance(status, int) or isinstance(status, bool):
            status = None
        if isinstance(exc, WbiRetryTimesExceedException):
            reason = 'The Bilibili SDK exhausted its WBI request retries.'
        elif code == -101 or status == 401:
            reason = f'Bilibili requires sign-in ({"API code " + str(code) if code is not None else "HTTP 401"}). Sign in on the fetching Mac.'
        elif code is not None:
            reason = f'Bilibili {"rejected the request" if code in {-403, -412, -352, -509} else "returned an error"} (API code {code}).'
        elif status is not None:
            reason = f'Bilibili returned HTTP {status}.'
        elif isinstance(exc, (TimeoutError, httpx.TimeoutException)):
            reason = 'The creator-list request timed out. Check the fetching Mac\'s internet connection.'
        elif isinstance(exc, httpx.TransportError):
            reason = f'Network request failed ({type(exc).__name__}). Check the fetching Mac\'s internet connection.'
        else:
            reason = f'Creator-list request failed ({type(exc).__name__}).'
        count = '' if collected is None else f' {collected}{"/" + str(requested) if requested is not None else ""} {item_kind} collected before failure.'
        raise ValueError(f'Video collection stopped on page {pn}. {reason}{count}') from exc


def video_total_from_response(videos: dict[str, Any]) -> int:
    page = videos.get("page", {})
    for key in ("count", "total"):
        try:
            return int(page[key])
        except (KeyError, TypeError, ValueError):
            continue
    return len(videos.get("list", {}).get("vlist", []))


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
        enriched["detail_error_code"] = getattr(exc, "code", None)
        enriched["detail_error_status"] = getattr(exc, "status", None)
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
    for key in ("owner", "tid", "tname", "duration"):
        if key in info:
            enriched[key] = info[key]
    return enriched
