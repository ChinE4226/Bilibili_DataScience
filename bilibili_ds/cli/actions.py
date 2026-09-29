"""Terminal fetching, analysis, and plotting workflows."""

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from bilibili_api import Credential, user
from bilibili_api.exceptions import NetworkException

from bilibili_ds import config
from bilibili_ds.accounts import (
    credential_for_requests,
    credential_from_env,
)
from bilibili_ds.analysis import (
    division_needs_up_relation,
    ratio_for_item,
    video_metric_value,
)
from bilibili_ds.cli.accounts import (
    credential_from_qrcode,
)
from bilibili_ds.cli.output import (
    print_aggregate_division_result,
    print_analysis_result,
    print_plot_result,
    print_single_video_division_result,
    print_video_entry,
)
from bilibili_ds.cli.prompts import (
    prompt_division_fields,
    prompt_division_mode,
    prompt_metric_value_range,
    prompt_plot_mode,
    prompt_published_time_position_range,
    prompt_published_time_range,
    prompt_video_selection_choice,
    prompt_video_stat_field,
)
from bilibili_ds.client import (
    close_bilibili_client,
    configure_bilibili_client,
    request_delay_seconds,
)
from bilibili_ds.plotting import (
    build_plot_points,
    save_line_plot,
)
from bilibili_ds.selection import (
    filter_items_by_metric_range,
    filter_items_by_published_time_range,
    sort_video_items,
)
from bilibili_ds.storage import (
    load_selected_up,
    load_uid,
    uid_from_up,
)
from bilibili_ds.videos import (
    fetch_latest_video_like,
    fetch_video_detail,
    fetch_video_summaries,
    video_total_from_response,
)


async def async_main(args: argparse.Namespace) -> None:
    configure_bilibili_client()
    uid = args.uid or load_uid(args.object_file)
    credential = credential_from_env()

    if args.login and credential is None:
        credential = await credential_from_qrcode(args.print_terminal_qrcode)

    try:
        result = await fetch_latest_video_like(uid, credential)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except NetworkException as exc:
        message = str(exc)
        if "Status Code: 412" in message or "Error Code: 412" in message:
            raise SystemExit(
                "Bilibili returned 412. Sign in with QR code, or save your Bilibili Cookie to "
                f"{config.COOKIE_FILE} and try again."
            ) from exc
        raise
    finally:
        await close_bilibili_client()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Get the like count of the latest video.")
    parser.add_argument(
        "--object-file",
        type=Path,
        default=config.UPS_FILE,
        help="JSON file containing the UP space URL. Default: %(default)s",
    )
    parser.add_argument("--uid", type=int, default=None, help="Directly specify the UP UID.")
    parser.add_argument("--login", action="store_true", help="Use QR code sign-in when no account cache is available.")
    parser.add_argument("--print-terminal-qrcode", action="store_true", help="Print the QR code in the terminal.")
    return parser.parse_args()


async def enrich_video_items(
    items: list[dict[str, Any]],
    credential: Credential | None,
    *,
    progress_label: str,
) -> list[dict[str, Any]]:
    enriched_items: list[dict[str, Any]] = []
    total = len(items)
    if total:
        print(progress_label)

    for index, item in enumerate(items, start=1):
        if index == 1 or index == total or index % 10 == 0:
            print(f"Fetching video details: {index}/{total}")
        enriched_items.append(await fetch_video_detail(item, credential))
        await asyncio.sleep(request_delay_seconds())

    return enriched_items


async def fetch_items_for_selection(
    uploader: Any,
    credential: Credential | None,
    total: int,
    selection: dict[str, Any],
    *,
    action_name: str,
) -> tuple[list[dict[str, Any]], str] | None:
    if selection["kind"] == "published_time_position_range":
        position_range = prompt_published_time_position_range(total, action_name=action_name)
        if position_range is None:
            return None
        start_number, end_number = position_range
        summaries = await fetch_video_summaries(uploader, end_number, user.VideoOrder.PUBDATE)
        selected_summaries = summaries[start_number - 1 : end_number]
        detailed_items = await enrich_video_items(
            selected_summaries,
            credential,
            progress_label="Fetching details for selected videos.",
        )
        return detailed_items, f"published-time ordered videos {start_number}-{end_number} (latest to oldest)"

    if selection["kind"] == "published_time_range":
        time_range = prompt_published_time_range(action_name=action_name)
        if time_range is None:
            return None
        start_timestamp, end_timestamp, range_label = time_range
        print(f"This selection needs scanning {total} video record(s) to apply the published time range.")
        summaries = await fetch_video_summaries(uploader, total, user.VideoOrder.PUBDATE)
        selected_summaries = filter_items_by_published_time_range(summaries, start_timestamp, end_timestamp)
        ordered_summaries = sort_video_items(selected_summaries, selection["sort_mode"])
        detailed_items = await enrich_video_items(
            ordered_summaries,
            credential,
            progress_label="Fetching details for selected videos.",
        )
        ordered_items = sort_video_items(detailed_items, selection["sort_mode"])
        return ordered_items, f"{selection['label']} from {range_label}"

    metric_range = prompt_metric_value_range(selection["range_label"], action_name=action_name)
    if metric_range is None:
        return None
    minimum_value, maximum_value, range_label = metric_range
    print(f"This selection needs scanning {total} video record(s) and fetching their details.")
    summaries = await fetch_video_summaries(uploader, total, user.VideoOrder.PUBDATE)
    detailed_items = await enrich_video_items(
        summaries,
        credential,
        progress_label="Fetching details before applying the metric range.",
    )
    selected_items = filter_items_by_metric_range(
        detailed_items,
        selection["stat_key"],
        minimum_value,
        maximum_value,
    )
    ordered_items = sort_video_items(selected_items, selection["sort_mode"])
    return ordered_items, f"{selection['range_label']} {range_label}"


def get_video_list() -> None:
    selected_up = load_selected_up()
    if selected_up is None:
        print("No UP is selected. Select an UP first.")
        return

    uid = uid_from_up(selected_up)
    credential = credential_for_requests()

    async def fetch_and_print() -> None:
        uploader = user.User(uid, credential=credential)
        try:
            first_page = await uploader.get_videos(pn=1, ps=1, order=user.VideoOrder.PUBDATE)
        except Exception as exc:
            print(f"Failed to fetch video list: {exc}")
            return

        total = video_total_from_response(first_page)
        if total <= 0:
            print("No videos found for this UP.")
            return

        selection = prompt_video_selection_choice(action_name="Video listing")
        if selection is None:
            return

        selected = await fetch_items_for_selection(
            uploader,
            credential,
            total,
            selection,
            action_name="Video listing",
        )
        if selected is None:
            return
        selected_items, selection_label = selected

        if not selected_items:
            print("No videos matched the selected range.")
            return

        print(f"Selection: {selection_label}")
        for index, item in enumerate(selected_items, start=1):
            print_video_entry(index, item)

    async def fetch_and_close() -> None:
        configure_bilibili_client()
        try:
            await fetch_and_print()
        finally:
            await close_bilibili_client()

    asyncio.run(fetch_and_close())


def get_mean_and_median() -> None:
    selected_up = load_selected_up()
    if selected_up is None:
        print("No UP is selected. Select an UP first.")
        return

    uid = uid_from_up(selected_up)
    credential = credential_for_requests()

    async def fetch_and_analyse() -> None:
        uploader = user.User(uid, credential=credential)
        try:
            first_page = await uploader.get_videos(pn=1, ps=1, order=user.VideoOrder.PUBDATE)
        except Exception as exc:
            print(f"Failed to fetch video list: {exc}")
            return

        total = video_total_from_response(first_page)
        if total <= 0:
            print("No videos found for this UP.")
            return

        selection = prompt_video_selection_choice(action_name="Analysis")
        if selection is None:
            return

        selected = await fetch_items_for_selection(
            uploader,
            credential,
            total,
            selection,
            action_name="Analysis",
        )
        if selected is None:
            return
        selected_items, selection_label = selected

        if not selected_items:
            print("No videos matched the selected range.")
            return

        print_analysis_result(
            selected_up=selected_up,
            selection_label=selection_label,
            items=selected_items,
        )

    async def fetch_and_close() -> None:
        configure_bilibili_client()
        try:
            await fetch_and_analyse()
        finally:
            await close_bilibili_client()

    asyncio.run(fetch_and_close())


def do_division() -> None:
    selected_up = load_selected_up()
    if selected_up is None:
        print("No UP is selected. Select an UP first.")
        return

    mode = prompt_division_mode()
    if mode is None:
        return

    division_fields = prompt_division_fields()
    if division_fields is None:
        return
    numerator_field, denominator_field = division_fields

    uid = uid_from_up(selected_up)
    credential = credential_for_requests()

    async def fetch_and_divide() -> None:
        uploader = user.User(uid, credential=credential)
        try:
            first_page = await uploader.get_videos(pn=1, ps=1, order=user.VideoOrder.PUBDATE)
        except Exception as exc:
            print(f"Failed to fetch video list: {exc}")
            return

        total = video_total_from_response(first_page)
        if total <= 0:
            print("No videos found for this UP.")
            return

        up_relation: dict[str, Any] | None = None
        if division_needs_up_relation(numerator_field, denominator_field):
            try:
                up_relation = await uploader.get_relation_info()
            except Exception as exc:
                print(f"Failed to fetch selected UP follower data: {exc}")
                return

        selection = prompt_video_selection_choice(action_name="Division")
        if selection is None:
            return

        selected = await fetch_items_for_selection(
            uploader,
            credential,
            total,
            selection,
            action_name="Division",
        )
        if selected is None:
            return
        selected_items, selection_label = selected

        if not selected_items:
            print("No videos matched the selected range.")
            return

        if mode == "single":
            print_single_video_division_result(
                selected_items,
                numerator_field,
                denominator_field,
                selection_label,
                up_relation,
            )
        else:
            print_aggregate_division_result(
                selected_items,
                numerator_field,
                denominator_field,
                selection_label,
                up_relation,
            )

    async def fetch_and_close() -> None:
        configure_bilibili_client()
        try:
            await fetch_and_divide()
        finally:
            await close_bilibili_client()

    asyncio.run(fetch_and_close())


def plot_data() -> None:
    selected_up = load_selected_up()
    if selected_up is None:
        print("No UP is selected. Select an UP first.")
        return

    mode = prompt_plot_mode()
    if mode is None:
        return

    if mode == "field":
        field = prompt_video_stat_field("Choose data to plot:")
        if field is None:
            return
        numerator_field = None
        denominator_field = None
    else:
        division_fields = prompt_division_fields(action_name="Plot")
        if division_fields is None:
            return
        numerator_field, denominator_field = division_fields
        field = None

    uid = uid_from_up(selected_up)
    credential = credential_for_requests()

    async def fetch_and_plot() -> None:
        uploader = user.User(uid, credential=credential)
        try:
            first_page = await uploader.get_videos(pn=1, ps=1, order=user.VideoOrder.PUBDATE)
        except Exception as exc:
            print(f"Failed to fetch video list: {exc}")
            return

        total = video_total_from_response(first_page)
        if total <= 0:
            print("No videos found for this UP.")
            return

        up_relation: dict[str, Any] | None = None
        if mode == "quotient" and division_needs_up_relation(numerator_field, denominator_field):
            try:
                up_relation = await uploader.get_relation_info()
            except Exception as exc:
                print(f"Failed to fetch selected UP follower data: {exc}")
                return

        selection = prompt_video_selection_choice(action_name="Plot")
        if selection is None:
            return

        selected = await fetch_items_for_selection(
            uploader,
            credential,
            total,
            selection,
            action_name="Plot",
        )
        if selected is None:
            return
        selected_items, selection_label = selected

        if not selected_items:
            print("No videos matched the selected range.")
            return

        if mode == "field":
            x_values, y_values, skipped = build_plot_points(
                selected_items,
                lambda item: video_metric_value(item, field["stat_key"]),
            )
            plot_label = field["label"]
            y_label = field["label"]
        else:
            x_values, y_values, skipped = build_plot_points(
                selected_items,
                lambda item: ratio_for_item(item, numerator_field, denominator_field, up_relation)[2],
            )
            plot_label = f"{numerator_field['label']} divided by {denominator_field['label']}"
            y_label = f"{numerator_field['label']} / {denominator_field['label']}"

        if not x_values:
            print("No plottable data was found in the selected videos.")
            return

        output_path = save_line_plot(
            selected_up=selected_up,
            selection_label=selection_label,
            plot_label=plot_label,
            y_label=y_label,
            x_values=x_values,
            y_values=y_values,
        )
        print_plot_result(output_path, len(x_values), skipped)

    async def fetch_and_close() -> None:
        configure_bilibili_client()
        try:
            await fetch_and_plot()
        finally:
            await close_bilibili_client()

    asyncio.run(fetch_and_close())
