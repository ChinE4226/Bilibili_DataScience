"""Interactive terminal sign-in and account workflows."""

import asyncio

from bilibili_api import Credential
from bilibili_api.login_v2 import QrCodeLogin, QrCodeLoginEvents
import qrcode

from bilibili_ds import config, state
from bilibili_ds.accounts import (
    build_account_record,
    check_account_condition,
    clear_active_account_cache,
    clear_all_account_caches,
    credential_for_requests,
    credential_from_dict,
    load_account_detail,
    load_account_records,
    save_account_record,
    unlink_if_exists,
)
from bilibili_ds.cli.output import (
    print_account_detail,
)
from bilibili_ds.client import (
    close_bilibili_client,
)
from bilibili_ds.storage import (
    write_json,
)


def compact_qrcode_terminal(data: str) -> str:
    qr = qrcode.QRCode(border=2)
    qr.add_data(data)
    qr.make(fit=True)
    matrix = qr.get_matrix()

    fg_black = "\033[30m"
    fg_white = "\033[37m"
    bg_black = "\033[40m"
    bg_white = "\033[47m"
    reset = "\033[0m"
    lines: list[str] = []

    for row_index in range(0, len(matrix), 2):
        top_row = matrix[row_index]
        bottom_row = matrix[row_index + 1] if row_index + 1 < len(matrix) else [False] * len(top_row)
        line_parts = []
        for top, bottom in zip(top_row, bottom_row):
            fg = fg_black if top else fg_white
            bg = bg_black if bottom else bg_white
            line_parts.append(f"{fg}{bg}▀")
        lines.append("".join(line_parts) + reset)
    return "\n".join(lines)


async def credential_from_qrcode(print_terminal_qrcode: bool = True) -> Credential:
    login = QrCodeLogin()
    await login.generate_qrcode()
    config.QRCODE_FILE.parent.mkdir(parents=True, exist_ok=True)
    login.get_qrcode_picture().to_file(str(config.QRCODE_FILE))

    print(f"The QR code has been saved to: {config.QRCODE_FILE}")
    if print_terminal_qrcode:
        qr_link = getattr(login, "_QrCodeLogin__qr_link", "")
        if qr_link:
            print(compact_qrcode_terminal(qr_link))
        else:
            print(login.get_qrcode_terminal())
    print("Scan the QR code with the signed-in Bilibili app to finish sign-in.")

    try:
        while True:
            event = await login.check_state()
            if event == QrCodeLoginEvents.DONE:
                credential = login.get_credential()
                record = await build_account_record(credential, source="qr")
                save_account_record(record)
                print(f"Sign-in successful. Cached account: {record['name']}.")
                return credential
            if event == QrCodeLoginEvents.TIMEOUT:
                raise TimeoutError("The QR code has expired. Run sign-in again.")
            await asyncio.sleep(2)
    finally:
        await close_bilibili_client()


def use_service_without_sign_in() -> None:
    state.USE_GUEST_MODE = True
    print("Guest mode enabled. Public requests will run without a signed-in account.")


def choose_cached_account() -> Credential | None:
    records = [record for record in load_account_records() if record.get("source") != "environment"]
    if not records:
        print("No cached accounts are available.")
        return None

    print("Available cached accounts:")
    for index, record in enumerate(records, start=1):
        uid_text = f"UID {record['uid']}" if record.get("uid") else "UID unknown"
        print(f"{index}. {record['name']} ({uid_text})")
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
        if not 0 <= index < len(records):
            print("Invalid selection.")
            continue

        record = records[index]
        credential = credential_from_dict(record["credential"])
        is_valid, error = asyncio.run(check_account_condition(credential))
        if is_valid:
            write_json(config.ACTIVE_ACCOUNT_FILE, {"id": record["id"]})
            print(f"Selected account: {record['name']}.")
            return credential
        if error:
            print(f"Could not check this account: {error}")
        else:
            print("That cached account is no longer valid.")
        return None


def sign_in() -> None:
    print("Sign-in options:")
    print("1. Select an available cached account")
    print("2. Sign in with a QR code")
    print("3. Use the service without signing in")
    print("0. Return to the menu")
    choice = input("-> ").strip()

    if choice == "0" or choice == "":
        print("Sign-in canceled.")
        return
    if choice == "1":
        if choose_cached_account() is not None:
            state.USE_GUEST_MODE = False
        return
    if choice == "2":
        try:
            if asyncio.run(credential_from_qrcode(print_terminal_qrcode=True)):
                state.USE_GUEST_MODE = False
        except TimeoutError as exc:
            print(f"Sign-in failed: {exc}")
        except Exception as exc:
            print(f"Unexpected error during sign-in: {exc}")
        return
    if choice == "3":
        use_service_without_sign_in()
        return

    print("Invalid sign-in choice.")


def sign_out() -> None:
    if state.USE_GUEST_MODE:
        print("Guest mode is active. No sign-in cache was changed.")
        return

    credential = credential_for_requests()
    is_valid, error = asyncio.run(check_account_condition(credential))
    if is_valid:
        print("The account credential currently in use is valid.")
    elif error:
        print(f"Could not check the account credential currently in use: {error}")
    else:
        print("No valid signed-in account is currently in use.")

    print("Sign-out options:")
    print("1. Sign out and keep all cached accounts")
    print("2. Sign out and remove the selected cached account")
    print("3. Sign out and remove all cached accounts")
    print("0. Return to the menu")
    choice = input("-> ").strip()

    if choice == "0" or choice == "":
        print("Sign-out canceled.")
        return
    if choice == "1":
        unlink_if_exists(config.ACTIVE_ACCOUNT_FILE)
        print("Cached accounts were kept.")
    elif choice == "2":
        removed = clear_active_account_cache()
        print(f"Removed {removed} cache file(s) for the selected account.")
    elif choice == "3":
        removed = clear_all_account_caches()
        print(f"Removed {removed} sign-in cache file(s).")
    else:
        print("Invalid sign-out choice.")
        return

    use_service_without_sign_in()


def view_account_detail() -> None:
    if state.USE_GUEST_MODE:
        print("Guest mode is active. Sign in to view account details.")
        return

    is_valid, detail, error = asyncio.run(load_account_detail(credential_for_requests()))
    if error:
        print(f"Could not load account details: {error}")
        return
    if not is_valid or detail is None:
        print("No valid signed-in account is available. Sign in again or use guest mode.")
        return
    print_account_detail(detail)
