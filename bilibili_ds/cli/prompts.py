"""Terminal input prompts and settings controls."""

from typing import Any

from bilibili_ds import config, state
from bilibili_ds.analysis import (
    division_field_choices,
)
from bilibili_ds.cli.output import (
    format_count,
)
from bilibili_ds.client import (
    request_delay_seconds,
)
from bilibili_ds.selection import (
    parse_datetime_input,
    parse_int_range_value,
    video_selection_choices,
)


def choose_from_list(items: list[dict[str, str]]) -> dict[str, str] | None:
    if not items:
        print("No items are available.")
        return None

    for index, item in enumerate(items, start=1):
        print(f"{index}. {item.get('name') or 'Unnamed'} - {item.get('space')}")
    print("0. Return")

    while True:
        choice = input("-> ").strip()
        if choice == "0" or choice == "":
            return None
        try:
            index = int(choice) - 1
        except ValueError:
            print("Enter a number.")
            continue
        if 0 <= index < len(items):
            return items[index]
        print("Invalid selection.")


def set_request_frequency() -> None:
    print(f"Current request frequency: {state.REQUEST_FREQUENCY:g} request(s) per second.")
    print(f"1. Reset to the default ({config.DEFAULT_REQUEST_FREQUENCY:g} request(s) per second)")
    print("2. Enter a custom request frequency")
    print("0. Return to the menu")
    choice = input("-> ").strip()

    if choice == "0" or choice == "":
        print("Request frequency was not changed.")
        return
    if choice == "1":
        state.REQUEST_FREQUENCY = config.DEFAULT_REQUEST_FREQUENCY
    elif choice == "2":
        frequency_input = input("Custom request frequency in requests per second: ").strip()
        try:
            new_frequency = float(frequency_input)
        except ValueError:
            print("Request frequency must be a number.")
            return
        if new_frequency <= 0:
            print("Request frequency must be greater than 0.")
            return
        state.REQUEST_FREQUENCY = new_frequency
    else:
        print("Invalid selection.")
        return

    print(
        f"Request frequency set to {state.REQUEST_FREQUENCY:g} request(s) per second "
        f"({request_delay_seconds():.3f} second delay)."
    )


def prompt_video_selection_choice(*, action_name: str) -> dict[str, Any] | None:
    choices = video_selection_choices()

    if action_name == "Video listing":
        print("Choose how to list videos:")
    else:
        print("Choose how to select videos:")
    for index, choice in enumerate(choices, start=1):
        print(f"{index}. {choice['label']}")
    print("0. Return to the menu")

    while True:
        raw_choice = input("-> ").strip()
        if raw_choice == "0" or raw_choice == "":
            print(f"{action_name} canceled.")
            return None
        try:
            choice_index = int(raw_choice) - 1
        except ValueError:
            print("Enter a number.")
            continue
        if 0 <= choice_index < len(choices):
            return choices[choice_index]
        print("Invalid selection.")


def prompt_published_time_position_range(total: int, *, action_name: str) -> tuple[int, int] | None:
    print(f"Enter the published-time ordered video number range. Available range: 1-{total}")
    print("Numbers are ordered by published time, latest to oldest.")
    print("0. Return to the menu")

    while True:
        start_input = input("Start number: ").strip()
        if start_input == "0" or start_input == "":
            print(f"{action_name} canceled.")
            return None
        end_input = input("End number: ").strip()
        if end_input == "0" or end_input == "":
            print(f"{action_name} canceled.")
            return None

        try:
            start = int(start_input)
            end = int(end_input)
        except ValueError:
            print("Enter numbers only.")
            continue

        if not 1 <= start <= total or not 1 <= end <= total:
            print(f"Both numbers must be from 1 to {total}.")
            continue
        if start > end:
            print("Start number must be smaller than or equal to end number.")
            continue
        return start, end


def prompt_published_time_range(*, action_name: str) -> tuple[int, int, str] | None:
    print("Enter published time range.")
    print("Format: YYYY-MM-DD or YYYY-MM-DD HH:MM:SS")
    print("0. Return to the menu")

    while True:
        start_input = input("Start time: ").strip()
        if start_input == "0" or start_input == "":
            print(f"{action_name} canceled.")
            return None
        end_input = input("End time: ").strip()
        if end_input == "0" or end_input == "":
            print(f"{action_name} canceled.")
            return None

        start_dt = parse_datetime_input(start_input)
        end_dt = parse_datetime_input(end_input, end_of_day=True)
        if start_dt is None or end_dt is None:
            print("Enter time as YYYY-MM-DD or YYYY-MM-DD HH:MM:SS.")
            continue
        if start_dt > end_dt:
            print("Start time must be earlier than or equal to end time.")
            continue

        label = f"{start_dt.isoformat(sep=' ')} to {end_dt.isoformat(sep=' ')}"
        return int(start_dt.timestamp()), int(end_dt.timestamp()), label


def prompt_metric_value_range(label: str, *, action_name: str) -> tuple[int | None, int | None, str] | None:
    print(f"Enter {label} range.")
    print("Use blank for no limit. Examples: 100k, 100,000, 2.5m.")
    print("0. Return to the menu")

    while True:
        start_input = input("Greater than: ").strip()
        if start_input == "0":
            print(f"{action_name} canceled.")
            return None
        end_input = input("Less than: ").strip()
        if end_input == "0":
            print(f"{action_name} canceled.")
            return None

        start = parse_int_range_value(start_input) if start_input else None
        end = parse_int_range_value(end_input) if end_input else None
        if (start_input and start is None) or (end_input and end is None):
            print("Enter non-negative numbers, optionally using k or m.")
            continue
        if start is None and end is None:
            print("Enter at least one boundary.")
            continue
        if start is not None and end is not None and start >= end:
            print("The lower boundary must be smaller than the upper boundary.")
            continue

        if start is not None and end is not None:
            label_text = f"greater than {format_count(start)} and less than {format_count(end)}"
        elif start is not None:
            label_text = f"greater than {format_count(start)}"
        else:
            label_text = f"less than {format_count(end)}"
        return start, end, label_text


def prompt_division_mode() -> str | None:
    print("Choose division mode:")
    print("1. Calculate the ratio for every selected video")
    print("2. Calculate one ratio for all selected videos")
    print("0. Return to the menu")

    while True:
        choice = input("-> ").strip()
        if choice == "0" or choice == "":
            print("Division canceled.")
            return None
        if choice == "1":
            return "single"
        if choice == "2":
            return "aggregate"
        print("Enter 1, 2, or 0.")


def prompt_stat_field(prompt_text: str, *, action_name: str = "Division") -> dict[str, str] | None:
    choices = division_field_choices()

    print(prompt_text)
    for index, field in enumerate(choices, start=1):
        print(f"{index}. {field['label']}")
    print("0. Return to the menu")

    while True:
        choice = input("-> ").strip()
        if choice == "0" or choice == "":
            print(f"{action_name} canceled.")
            return None
        try:
            index = int(choice) - 1
        except ValueError:
            print("Enter a number.")
            continue
        if 0 <= index < len(choices):
            return choices[index]
        print("Invalid selection.")


def prompt_division_fields(*, action_name: str = "Division") -> tuple[dict[str, str], dict[str, str]] | None:
    numerator = prompt_stat_field("Choose numerator data:", action_name=action_name)
    if numerator is None:
        return None

    denominator = prompt_stat_field("Choose denominator data:", action_name=action_name)
    if denominator is None:
        return None

    return numerator, denominator


def prompt_plot_mode() -> str | None:
    print("Choose plot mode:")
    print("1. Plot one data field of selected videos")
    print("2. Plot the quotient of one data set divided by another")
    print("0. Return to the menu")

    while True:
        choice = input("-> ").strip()
        if choice == "0" or choice == "":
            print("Plot canceled.")
            return None
        if choice == "1":
            return "field"
        if choice == "2":
            return "quotient"
        print("Enter 1, 2, or 0.")


def prompt_video_stat_field(prompt_text: str) -> dict[str, str] | None:
    choices = [
        {"field": field_key, "label": label, "stat_key": stat_key}
        for field_key, label, stat_key in config.VIDEO_STAT_FIELDS
    ]

    print(prompt_text)
    for index, field in enumerate(choices, start=1):
        print(f"{index}. {field['label']}")
    print("0. Return to the menu")

    while True:
        choice = input("-> ").strip()
        if choice == "0" or choice == "":
            print("Plot canceled.")
            return None
        try:
            index = int(choice) - 1
        except ValueError:
            print("Enter a number.")
            continue
        if 0 <= index < len(choices):
            return choices[index]
        print("Invalid selection.")
