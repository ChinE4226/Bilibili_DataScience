"""Interactive terminal creator selection and details."""

import asyncio

from bilibili_ds import config
from bilibili_ds.cli.output import (
    print_selected_up_details,
)
from bilibili_ds.cli.prompts import (
    choose_from_list,
)
from bilibili_ds.storage import (
    load_ups,
    merge_up_entries,
    normalize_up,
    save_selected_up,
    save_ups,
)
from bilibili_ds.videos import (
    fetch_selected_up_details,
)


def select_an_up() -> None:
    entries = load_ups()

    while True:
        print("Select UP:")
        print("1. Choose from available UPs")
        print("2. Search UPs")
        print("3. Add a new UP")
        print(f"4. Show UP storage file path ({config.UPS_FILE})")
        print("0. Return to the menu")
        choice = input("-> ").strip()

        if choice == "0" or choice == "":
            print("UP selection canceled.")
            return
        if choice == "1":
            chosen = choose_from_list(entries)
            if chosen is not None:
                save_selected_up(chosen)
                print(f"Selected UP: {chosen['name']}")
                return
            continue
        if choice == "2":
            query = input("Search by name or UID (0 to return): ").strip().lower()
            if query == "0" or query == "":
                continue
            results = [
                entry
                for entry in entries
                if query in entry["name"].lower() or query == entry["uid"] or query in entry["space"]
            ]
            if not results:
                print("No matching UPs were found.")
                continue
            chosen = choose_from_list(results)
            if chosen is not None:
                save_selected_up(chosen)
                print(f"Selected UP: {chosen['name']}")
                return
            continue
        if choice == "3":
            name = input("Enter UP display name (0 to return): ").strip()
            if name == "0" or name == "":
                continue
            space = input("Enter space URL, for example https://space.bilibili.com/12345 (0 to return): ").strip()
            if space == "0" or space == "":
                continue
            normalized = normalize_up({"name": name, "space": space})
            if normalized is None:
                print("Cannot parse UID from that URL.")
                continue
            entries.append(normalized)
            entries = merge_up_entries(entries)
            save_ups(entries)
            save_selected_up(normalized)
            print(f"Added and selected UP: {normalized['name']}")
            return
        if choice == "4":
            print(f"UP list file: {config.UPS_FILE}")
            continue

        print("Invalid selection.")


def view_selected_up_account_details() -> None:
    details, error = asyncio.run(fetch_selected_up_details())
    if error:
        print(f"Could not load selected UP details: {error}")
        return
    if details is None:
        print("No selected UP details were returned.")
        return

    print_selected_up_details(details)
