"""Browser list, analysis, division, and plotting operations."""

from __future__ import annotations

from typing import Any

from bilibili_ds.web.creators import selected_up
from bilibili_ds.web.plots import save_web_plot_png
from bilibili_ds.web.progress import set_progress
from bilibili_ds.web.serializers import (
    analyse_items,
    field_by_name,
    field_value,
    ratio_value,
    serialize_video,
)
from bilibili_ds.web.videos import fetch_followers, fetch_selected_video_items


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
