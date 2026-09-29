"""Terminal menu and command dispatch."""

from bilibili_ds import state
from bilibili_ds.accounts import (
    account_condition_summary,
)
from bilibili_ds.cli.accounts import (
    sign_in,
    sign_out,
    view_account_detail,
)
from bilibili_ds.cli.actions import (
    do_division,
    get_mean_and_median,
    get_video_list,
    plot_data,
)
from bilibili_ds.cli.creators import (
    select_an_up,
    view_selected_up_account_details,
)
from bilibili_ds.cli.prompts import (
    set_request_frequency,
)
from bilibili_ds.storage import (
    load_ups,
    selected_up_summary,
)


def print_main_menu() -> None:
    print("")
    print("Menu")
    print(f"Account: {account_condition_summary()}")
    print(f"Selected UP: {selected_up_summary()}")
    print(f"Request frequency: {state.REQUEST_FREQUENCY:g} request(s) per second")
    print("1. Sign in")
    print("2. Sign out")
    print("3. View account details")
    print("4. Set request frequency")
    print("5. Select an UP")
    print("6. View the selected UP's account details")
    print("7. Get the video list with details")
    print("8. Calculate the mean and median of the data")
    print("9. Divide one data set by another")
    print("10. Plot the data")
    print("0. Exit")


def run_menu() -> None:
    load_ups()
    while True:
        print_main_menu()
        choice = input("-> ").strip()
        print("")

        if choice == "1":
            sign_in()
        elif choice == "2":
            sign_out()
        elif choice == "3":
            view_account_detail()
        elif choice == "4":
            set_request_frequency()
        elif choice == "5":
            select_an_up()
        elif choice == "6":
            view_selected_up_account_details()
        elif choice == "7":
            get_video_list()
        elif choice == "8":
            get_mean_and_median()
        elif choice == "9":
            do_division()
        elif choice == "10":
            plot_data()
        elif choice == "0":
            break
        else:
            print("Invalid menu choice.")
