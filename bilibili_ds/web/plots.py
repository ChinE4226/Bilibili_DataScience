"""Browser plot rendering and saved plot listings."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
from typing import Any

from bilibili_ds import config, plotting
from bilibili_ds.plotting import mdates, ticker


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
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_up_name = re.sub(r"[^\w.-]+", "_", selected.get("name", ""), flags=re.UNICODE).strip("_")[:40]
    up_part = f"{safe_up_name}_{selected['uid']}" if safe_up_name else selected["uid"]
    safe_label = re.sub(r"[^\w.-]+", "_", plot_label, flags=re.UNICODE).strip("_")[:80] or "plot"
    return config.PLOTS_DIR / f"{up_part}_{timestamp}_{safe_label}.png"


def save_web_plot_png(
    selected: dict[str, str],
    selection_label: str,
    plot_label: str,
    y_label: str,
    points: list[dict[str, Any]],
) -> str | None:
    if not points:
        return None

    config.PLOTS_DIR.mkdir(parents=True, exist_ok=True)
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

    figure, axis = plotting.plt.subplots(figsize=(13, 7))
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
    plotting.plt.close(figure)
    return output_path.name
