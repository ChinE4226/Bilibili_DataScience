"""Headless plot preparation and PNG rendering."""

from datetime import datetime
import os
from pathlib import Path
import re
from typing import Any

from bilibili_ds import config
from bilibili_ds.selection import (
    ordered_by_published_time,
    video_published_timestamp,
)

# Matplotlib's cache paths and headless backend must be set before pyplot loads.
os.environ.setdefault("MPLCONFIGDIR", str(config.RUNTIME_DIR / "matplotlib"))
os.environ.setdefault("XDG_CACHE_HOME", str(config.RUNTIME_DIR / "cache"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import dates as mdates
from matplotlib import ticker


def plot_file_path(selected_up: dict[str, str], plot_label: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_up_name = re.sub(r"[^\w.-]+", "_", selected_up.get("name", ""), flags=re.UNICODE).strip("_")[:40]
    up_part = f"{safe_up_name}_{selected_up['uid']}" if safe_up_name else selected_up["uid"]
    safe_label = re.sub(r"[^\w.-]+", "_", plot_label, flags=re.UNICODE).strip("_")[:80] or "plot"
    return config.PLOTS_DIR / f"{up_part}_{timestamp}_{safe_label}.png"


def build_plot_points(
    items: list[dict[str, Any]],
    value_getter: Any,
) -> tuple[list[datetime], list[float], int]:
    x_values: list[datetime] = []
    y_values: list[float] = []
    skipped = 0

    for item in ordered_by_published_time(items):
        published_time = video_published_timestamp(item)
        value = value_getter(item)
        if published_time is None or value is None:
            skipped += 1
            continue
        x_values.append(datetime.fromtimestamp(published_time))
        y_values.append(float(value))

    return x_values, y_values, skipped


def save_line_plot(
    *,
    selected_up: dict[str, str],
    selection_label: str,
    plot_label: str,
    y_label: str,
    x_values: list[datetime],
    y_values: list[float],
) -> Path:
    config.PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = plot_file_path(selected_up, plot_label)
    y_min = min(y_values)
    y_max = max(y_values)
    y_spread = y_max - y_min
    y_pad = max(y_spread * 0.12, abs(y_max) * 0.03, 1.0) if y_spread else max(abs(y_max) * 0.12, 1.0)

    figure, axis = plt.subplots(figsize=(13, 7))
    axis.plot(x_values, y_values, marker="o", linewidth=2.0, markersize=4.5)
    axis.set_title(f"{selected_up['name']} - {plot_label}")
    axis.set_xlabel("Published time")
    axis.set_ylabel(y_label)
    axis.set_ylim(y_min - y_pad, y_max + y_pad)
    axis.margins(x=0.03)
    axis.grid(True, linewidth=0.5, alpha=0.5)
    axis.yaxis.set_major_locator(ticker.MaxNLocator(nbins=7))
    axis.yaxis.set_major_formatter(ticker.StrMethodFormatter("{x:,.2f}"))
    axis.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=8))
    axis.xaxis.set_major_formatter(mdates.ConciseDateFormatter(axis.xaxis.get_major_locator()))
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
    plt.close(figure)
    return output_path
