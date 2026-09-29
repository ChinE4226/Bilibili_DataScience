"""Terminal formatting and result display."""

from datetime import datetime
import json
from pathlib import Path
from typing import Any

from bilibili_ds.analysis import (
    aggregate_division_label,
    aggregate_division_value,
    calculate_metric_summary,
    division_needs_up_relation,
    ratio_for_item,
)
from bilibili_ds.selection import (
    video_published_timestamp,
)


def print_account_detail(detail: dict[str, Any]) -> None:
    official = detail.get("official") if isinstance(detail.get("official"), dict) else {}
    level_progress = detail.get("level_exp") if isinstance(detail.get("level_exp"), dict) else {}
    fields = [
        ("UID", detail.get("mid")),
        ("Name", detail.get("name") or detail.get("uname")),
        ("Level", detail.get("level")),
        ("Experience", level_progress.get("current_exp")),
        ("Coins", detail.get("coins")),
        ("Moral", detail.get("moral")),
        ("Sex", detail.get("sex")),
        ("Birthday", detail.get("birthday")),
        ("Signature", detail.get("sign")),
        ("Official title", official.get("title")),
    ]

    print("Account details:")
    printed = 0
    for label, value in fields:
        if value not in (None, ""):
            print(f"{label}: {value}")
            printed += 1
    if printed == 0:
        print(json.dumps(detail, ensure_ascii=False, indent=2))


def format_count(value: Any) -> str:
    if value in (None, ""):
        return "Unknown"
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


def format_video_published_time(item: dict[str, Any]) -> str:
    timestamp = video_published_timestamp(item)
    if timestamp is None:
        return "Unknown"
    try:
        return datetime.fromtimestamp(timestamp).isoformat(sep=" ")
    except Exception:
        return str(timestamp)


def print_video_entry(index: int, item: dict[str, Any]) -> None:
    title = item.get("title") or "(no title)"
    bvid = item.get("bvid")
    aid = item.get("aid")
    stat = item.get("stat") if isinstance(item.get("stat"), dict) else {}

    print(f"{index}. {title}")
    print(f"   BVID: {bvid}  AID: {aid}  Published time: {format_video_published_time(item)}")
    print(
        f"   Views: {format_count(stat.get('view'))}  Likes: {format_count(stat.get('like'))}  "
        f"Replies: {format_count(stat.get('reply'))}  Favorites: {format_count(stat.get('favorite'))}  "
        f"Coins: {format_count(stat.get('coin'))}  Shares: {format_count(stat.get('share'))}"
    )
    if item.get("detail_error"):
        print(f"   (Failed to fetch video details: {item['detail_error']})")


def format_analysis_number(value: float | int | None) -> str:
    if value is None:
        return "Unknown"
    if isinstance(value, float) and not value.is_integer():
        return f"{value:,.2f}"
    return f"{int(value):,}"


def print_analysis_result(
    *,
    selected_up: dict[str, str],
    selection_label: str,
    items: list[dict[str, Any]],
) -> None:
    print("Analysis result")
    print(f"UP: {selected_up['name']} (UID {selected_up['uid']})")
    print(f"Selection: {selection_label}")
    print(f"Selected videos: {len(items)}")

    summaries = calculate_metric_summary(items)
    print("")
    print(f"{'Metric':<12}{'Data count':>12}{'Mean':>18}{'Median':>18}")
    for summary in summaries:
        print(
            f"{summary['label']:<12}"
            f"{summary['count']:>12}"
            f"{format_analysis_number(summary['mean']):>18}"
            f"{format_analysis_number(summary['median']):>18}"
        )


def format_ratio(value: float | None) -> str:
    if value is None:
        return "Undefined"
    return f"{value:,.6f} ({value * 100:,.2f}%)"


def print_single_video_division_result(
    items: list[dict[str, Any]],
    numerator_field: dict[str, str],
    denominator_field: dict[str, str],
    selection_label: str,
    up_relation: dict[str, Any] | None = None,
) -> None:
    print("Division result for every selected video")
    print(f"Selection: {selection_label}")
    print(f"Ratio: {numerator_field['label']} / {denominator_field['label']}")
    print(f"Selected videos: {len(items)}")

    skipped = 0
    for index, item in enumerate(items, start=1):
        numerator, denominator, ratio = ratio_for_item(
            item,
            numerator_field,
            denominator_field,
            up_relation,
        )
        if ratio is None:
            skipped += 1
        title = item.get("title") or "(no title)"
        print(f"{index}. {title}")
        print(f"   Published time: {format_video_published_time(item)}")
        print(
            f"   {numerator_field['label']}: {format_count(numerator)}  "
            f"{denominator_field['label']}: {format_count(denominator)}  "
            f"Ratio: {format_ratio(ratio)}"
        )

    if skipped:
        print(f"Skipped ratio calculation for {skipped} video(s) with missing data or zero denominator.")


def print_aggregate_division_result(
    items: list[dict[str, Any]],
    numerator_field: dict[str, str],
    denominator_field: dict[str, str],
    selection_label: str,
    up_relation: dict[str, Any] | None = None,
) -> None:
    numerator_summary = aggregate_division_value(items, numerator_field, up_relation)
    denominator_summary = aggregate_division_value(items, denominator_field, up_relation)
    numerator_total = numerator_summary["value"]
    denominator_total = denominator_summary["value"]

    ratio = (
        None
        if numerator_total is None or denominator_total in (None, 0)
        else numerator_total / denominator_total
    )

    print("Division result for all selected videos")
    print(f"Selection: {selection_label}")
    selected_count = len(items)
    print(
        f"Ratio: {aggregate_division_label(numerator_field, selected_count)} / "
        f"{aggregate_division_label(denominator_field, selected_count)}"
    )
    print(f"Selected videos: {selected_count}")
    print(f"{aggregate_division_label(numerator_field, selected_count)}: {format_count(numerator_total)}")
    print(f"{aggregate_division_label(denominator_field, selected_count)}: {format_count(denominator_total)}")
    if numerator_summary["missing"] or denominator_summary["missing"]:
        print(
            "Missing data: "
            f"{numerator_field['label']} {numerator_summary['missing']}, "
            f"{denominator_field['label']} {denominator_summary['missing']}"
        )
    if division_needs_up_relation(numerator_field, denominator_field):
        print("Followers is multiplied by the selected video count in aggregate mode.")
    print(f"Ratio: {format_ratio(ratio)}")


def print_selected_up_details(details: dict[str, Any]) -> None:
    profile = details.get("profile", {})
    relation = details.get("relation", {})
    up_stat = details.get("up_stat", {})
    official = profile.get("official") if isinstance(profile.get("official"), dict) else {}

    print("Selected UP details:")
    print(f"UID: {profile.get('mid') or details.get('selected', {}).get('uid')}")
    print(f"Name: {profile.get('name') or details.get('selected', {}).get('name')}")
    print(f"Signature: {profile.get('sign') or 'None'}")
    if official.get("title"):
        print(f"Official title: {official.get('title')}")
    print(f"Followers: {format_count(relation.get('follower'))}")
    print(f"Following: {format_count(relation.get('following'))}")
    print(f"Videos: {format_count(details.get('video_total'))}")
    if up_stat:
        print(f"Total video views: {format_count(up_stat.get('archive', {}).get('view'))}")
        print(f"Total likes: {format_count(up_stat.get('likes'))}")


def print_plot_result(output_path: Path, plotted_count: int, skipped_count: int) -> None:
    print(f"Plotted points: {plotted_count}")
    if skipped_count:
        print(f"Skipped videos with missing published time, missing data, or zero denominator: {skipped_count}")
    print(f"Plot saved to: {output_path}")
