"""Browser plot rendering and saved plot listings."""

from __future__ import annotations

from datetime import datetime
from collections import OrderedDict
from copy import deepcopy
from pathlib import Path
import re
import threading
from typing import Any
from uuid import uuid4

from bilibili_ds import config, plotting
from bilibili_ds.plotting import mdates


# Unsaved snapshots are bounded and never touch disk. The lock also serializes
# matplotlib exports, which are not safe to run on concurrent request threads.
PENDING_PLOT_LIMIT = 20
_pending_plots: OrderedDict[str, dict[str, Any]] = OrderedDict()
_plot_lock = threading.Lock()


def prepare_plot(
    selected: dict[str, str], selection_label: str, plot_label: str,
    y_label: str, points: list[dict[str, Any]],
) -> str | None:
    if not points:
        return None
    plot_id = uuid4().hex
    snapshot = deepcopy({"selected": selected, "selection_label": selection_label,
                         "plot_label": plot_label, "y_label": y_label, "points": points})
    with _plot_lock:
        _pending_plots[plot_id] = snapshot
        while len(_pending_plots) > PENDING_PLOT_LIMIT:
            _pending_plots.popitem(last=False)
    return plot_id


def save_prepared_plot(plot_id: Any) -> dict[str, str]:
    with _plot_lock:
        snapshot = _pending_plots.get(plot_id) if isinstance(plot_id, str) else None
        if snapshot is None:
            raise ValueError("This plot has expired. Generate it again before saving.")
        name = snapshot.get("file")
        if not name or not (config.PLOTS_DIR / name).is_file():
            name = save_web_plot_png(**{key: value for key, value in snapshot.items() if key != "file"})
            snapshot["file"] = name
        return {"name": name, "url": f"/plots/{name}"}


def plot_entries() -> list[dict[str, Any]]:
    if not config.PLOTS_DIR.exists():
        return []

    entries = []
    for path in sorted(config.PLOTS_DIR.glob("*.png"), key=lambda item: item.stat().st_mtime, reverse=True):
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
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    safe_creator_name = re.sub(r"[^\w.-]+", "_", selected.get("name", ""), flags=re.UNICODE).strip("_")[:40]
    creator_part = f"{safe_creator_name}_{selected['uid']}" if safe_creator_name else selected["uid"]
    safe_label = re.sub(r"[^\w.-]+", "_", plot_label, flags=re.UNICODE).strip("_")[:80] or "plot"
    return config.PLOTS_DIR / f"{creator_part}_{timestamp}_{safe_label}.png"


def save_web_plot_png(
    selected: dict[str, str],
    selection_label: str,
    plot_label: str,
    y_label: str,
    points: list[dict[str, Any]],
) -> str | None:
    if not points:
        return None

    points = sorted(points, key=lambda point: str(point["label"]))
    config.PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = plot_file_path(selected, plot_label)
    parsed_dates = [
        datetime.strptime(str(point["label"]), "%Y-%m-%d %H:%M:%S")
        for point in points
        if re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", str(point["label"]))
    ]
    x_values = parsed_dates if len(parsed_dates) == len(points) else list(range(1, len(points) + 1))
    y_values = [float(point["value"]) for point in points]

    figure, axis = plotting.plt.subplots(figsize=(13, 7))
    axis.plot(x_values, y_values, marker="o", linewidth=2.0, markersize=4.5)
    axis.set_title(f"{selected['name']} (UID {selected['uid']}) - {plot_label}")
    axis.set_xlabel("Published time")
    axis.set_ylabel(y_label)
    plotting.configure_y_axis(axis, y_values)
    axis.margins(x=0.03)
    axis.grid(True, linewidth=0.5, alpha=0.5)
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
    try:
        figure.savefig(output_path, dpi=160)
    finally:
        plotting.plt.close(figure)
    return output_path.name
