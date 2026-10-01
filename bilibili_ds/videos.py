"""Video response handling and detail fetching used by the website."""

from typing import Any

from bilibili_api import Credential, video


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
