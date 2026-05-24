import argparse
import asyncio
import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import qrcode
from bilibili_api import Credential, get_client, request_settings, user, video
from bilibili_api.exceptions import NetworkException
from bilibili_api.login_v2 import QrCodeLogin, QrCodeLoginEvents


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OBJECTS_DIR = PROJECT_ROOT / "objects"
RUNTIME_DIR = PROJECT_ROOT / ".runtime"

UPS_FILE = OBJECTS_DIR / "ups.json"

QRCODE_FILE = RUNTIME_DIR / "bilibili_qrcode.png"
COOKIE_FILE = RUNTIME_DIR / "bilibili_cookie.txt"
LEGACY_CREDENTIAL_FILE = RUNTIME_DIR / "bilibili_credential.json"
ACCOUNTS_DIR = RUNTIME_DIR / "accounts"
ACTIVE_ACCOUNT_FILE = RUNTIME_DIR / "active_account.json"

DEFAULT_REQUEST_FREQUENCY = 4.0
REQUEST_FREQUENCY = DEFAULT_REQUEST_FREQUENCY
USE_GUEST_MODE = False


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_uid_from_space(space: str) -> int:
    match = re.search(r"space\.bilibili\.com/(\d+)", space)
    if not match:
        raise ValueError(f"Cannot parse Bilibili UID from {space!r}")
    return int(match.group(1))


def uid_from_up(entry: dict[str, Any]) -> int:
    if entry.get("uid"):
        return int(entry["uid"])
    return parse_uid_from_space(str(entry.get("space", "")))


def load_uid(object_file: Path) -> int:
    data = read_json(object_file, {})
    if isinstance(data, dict) and data.get("selected_uid"):
        for entry in data.get("ups", []):
            if str(entry.get("uid")) == str(data["selected_uid"]):
                return uid_from_up(entry)
    return uid_from_up(data)


def normalize_up(entry: dict[str, Any]) -> dict[str, str] | None:
    space = str(entry.get("space") or "").strip()
    if not space:
        uid = str(entry.get("uid") or entry.get("mid") or "").strip()
        if not uid.isdigit():
            return None
        space = f"https://space.bilibili.com/{uid}"

    try:
        uid = parse_uid_from_space(space)
    except ValueError:
        return None

    name = str(entry.get("name") or entry.get("uname") or f"UP-{uid}").strip()
    return {"name": name, "space": space, "uid": str(uid)}


def extract_ups_from_text(raw: str) -> list[dict[str, str]]:
    pattern = r'\{\s*"name"\s*:\s*"([^"]+)"\s*,\s*"space"\s*:\s*"([^"]+)"\s*\}'
    return [
        normalized
        for name, space in re.findall(pattern, raw)
        if (normalized := normalize_up({"name": name, "space": space})) is not None
    ]


def normalize_up_entries(entries: Any) -> list[dict[str, str]]:
    if isinstance(entries, dict):
        entries = [entries]
    if not isinstance(entries, list):
        return []
    return [
        normalized
        for entry in entries
        if isinstance(entry, dict)
        if (normalized := normalize_up(entry)) is not None
    ]


def merge_up_entries(entries: list[dict[str, str]]) -> list[dict[str, str]]:
    merged: dict[str, dict[str, str]] = {}
    for entry in entries:
        key = entry["uid"]
        if key not in merged or merged[key].get("name", "").startswith("UP-"):
            merged[key] = entry
    return sorted(merged.values(), key=lambda item: item["name"].lower())


def default_up_store() -> dict[str, Any]:
    return {"selected_uid": None, "ups": [], "details_by_uid": {}}


def load_up_store() -> dict[str, Any]:
    raw = read_json(UPS_FILE, default_up_store())
    if isinstance(raw, list):
        store = {"selected_uid": None, "ups": normalize_up_entries(raw), "details_by_uid": {}}
    elif isinstance(raw, dict):
        store = {
            "selected_uid": str(raw["selected_uid"]) if raw.get("selected_uid") else None,
            "ups": normalize_up_entries(raw.get("ups", [])),
            "details_by_uid": raw.get("details_by_uid", {}) if isinstance(raw.get("details_by_uid"), dict) else {},
        }
    else:
        store = default_up_store()

    store["ups"] = merge_up_entries(store["ups"])
    known_uids = {entry["uid"] for entry in store["ups"]}
    if store["selected_uid"] not in known_uids:
        store["selected_uid"] = store["ups"][0]["uid"] if store["ups"] else None
    write_json(UPS_FILE, store)
    return store


def save_up_store(store: dict[str, Any]) -> None:
    normalized_store = {
        "selected_uid": str(store["selected_uid"]) if store.get("selected_uid") else None,
        "ups": merge_up_entries(normalize_up_entries(store.get("ups", []))),
        "details_by_uid": store.get("details_by_uid", {}) if isinstance(store.get("details_by_uid"), dict) else {},
    }
    write_json(UPS_FILE, normalized_store)


def load_ups() -> list[dict[str, str]]:
    return load_up_store()["ups"]


def save_ups(entries: list[dict[str, str]]) -> None:
    store = load_up_store()
    store["ups"] = merge_up_entries(entries)
    save_up_store(store)


def load_selected_up() -> dict[str, str] | None:
    store = load_up_store()
    selected_uid = str(store["selected_uid"]) if store.get("selected_uid") else None
    for entry in store["ups"]:
        if entry["uid"] == selected_uid:
            return entry
    return None


def save_selected_up(entry: dict[str, str]) -> None:
    normalized = normalize_up(entry)
    if normalized is None:
        raise ValueError("Cannot save an invalid UP entry.")
    store = load_up_store()
    store["ups"] = merge_up_entries([*store["ups"], normalized])
    store["selected_uid"] = normalized["uid"]
    save_up_store(store)


def save_selected_up_details(details: dict[str, Any]) -> None:
    selected = details.get("selected", {})
    uid = str(selected.get("uid") or details.get("profile", {}).get("mid") or "")
    if not uid:
        return
    store = load_up_store()
    store.setdefault("details_by_uid", {})[uid] = details
    save_up_store(store)


def selected_up_summary() -> str:
    selected_up = load_selected_up()
    if selected_up is None:
        return "None"
    return f"{selected_up['name']} (UID {selected_up['uid']})"


def parse_cookie_header(cookie_header: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for item in cookie_header.split(";"):
        if "=" not in item:
            continue
        key, value = item.strip().split("=", 1)
        if key:
            cookies[key] = value
    return cookies


def credential_from_cookie_header(cookie_header: str) -> Credential:
    return Credential.from_cookies(parse_cookie_header(cookie_header))


def credential_to_dict(credential: Credential) -> dict[str, str | None]:
    return {
        "sessdata": credential.sessdata,
        "bili_jct": credential.bili_jct,
        "dedeuserid": credential.dedeuserid,
        "buvid3": credential.buvid3,
        "buvid4": credential.buvid4,
        "ac_time_value": credential.ac_time_value,
    }


def credential_from_dict(data: dict[str, Any]) -> Credential:
    return Credential(
        sessdata=data.get("sessdata"),
        bili_jct=data.get("bili_jct"),
        dedeuserid=data.get("dedeuserid"),
        buvid3=data.get("buvid3"),
        buvid4=data.get("buvid4"),
        ac_time_value=data.get("ac_time_value"),
    )


def credential_from_environment() -> Credential | None:
    cookie_header = os.getenv("BILI_COOKIE")
    if cookie_header:
        return credential_from_cookie_header(cookie_header)

    if COOKIE_FILE.exists():
        cookie_header = COOKIE_FILE.read_text(encoding="utf-8").strip()
        if cookie_header:
            return credential_from_cookie_header(cookie_header)

    sessdata = os.getenv("BILI_SESSDATA")
    bili_jct = os.getenv("BILI_JCT")
    dedeuserid = os.getenv("BILI_DEDEUSERID")
    buvid3 = os.getenv("BILI_BUVID3")
    buvid4 = os.getenv("BILI_BUVID4")
    ac_time_value = os.getenv("BILI_AC_TIME_VALUE")
    if not any([sessdata, bili_jct, dedeuserid, buvid3, buvid4, ac_time_value]):
        return None

    return Credential(
        sessdata=sessdata,
        bili_jct=bili_jct,
        dedeuserid=dedeuserid,
        buvid3=buvid3,
        buvid4=buvid4,
        ac_time_value=ac_time_value,
    )


def account_id_from_credential(credential: Credential) -> str:
    if credential.dedeuserid:
        return str(credential.dedeuserid)
    digest_source = "|".join(
        value or ""
        for value in [
            credential.sessdata,
            credential.bili_jct,
            credential.buvid3,
            credential.buvid4,
        ]
    )
    digest = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()[:16]
    return f"account-{digest}"


def account_path(account_id: str) -> Path:
    safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", account_id)
    return ACCOUNTS_DIR / f"{safe_id}.json"


def account_record_from_credential(
    credential: Credential,
    *,
    name: str | None = None,
    uid: str | None = None,
    source: str = "cache",
) -> dict[str, Any]:
    account_id = str(uid or credential.dedeuserid or account_id_from_credential(credential))
    return {
        "id": account_id,
        "name": name or f"Account {account_id}",
        "uid": str(uid or credential.dedeuserid or ""),
        "source": source,
        "credential": credential_to_dict(credential),
    }


async def build_account_record(credential: Credential, source: str) -> dict[str, Any]:
    account_id = account_id_from_credential(credential)
    name = f"Account {account_id}"
    uid = str(credential.dedeuserid or "")

    configure_bilibili_client()
    try:
        if await credential.check_valid():
            info = await user.get_self_info(credential)
            uid = str(info.get("mid") or uid)
            name = str(info.get("name") or info.get("uname") or name)
    except Exception:
        pass
    finally:
        await close_bilibili_client()

    return account_record_from_credential(credential, name=name, uid=uid, source=source)


def load_account_record(path: Path) -> dict[str, Any] | None:
    data = read_json(path, {})
    if not isinstance(data, dict):
        return None
    credential_data = data.get("credential")
    if not isinstance(credential_data, dict):
        return None
    credential = credential_from_dict(credential_data)
    account_id = str(data.get("id") or account_id_from_credential(credential))
    return {
        "id": account_id,
        "name": str(data.get("name") or f"Account {account_id}"),
        "uid": str(data.get("uid") or credential.dedeuserid or ""),
        "source": str(data.get("source") or "cache"),
        "credential": credential_to_dict(credential),
        "path": path,
    }


def legacy_account_record() -> dict[str, Any] | None:
    data = read_json(LEGACY_CREDENTIAL_FILE, {})
    if not isinstance(data, dict) or not data:
        return None
    try:
        credential = credential_from_dict(data)
    except Exception:
        return None
    return account_record_from_credential(credential, source="legacy")


def load_account_records() -> list[dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    if ACCOUNTS_DIR.exists():
        for path in sorted(ACCOUNTS_DIR.glob("*.json")):
            record = load_account_record(path)
            if record is not None:
                records[record["id"]] = record

    legacy_record = legacy_account_record()
    if legacy_record is not None and legacy_record["id"] not in records:
        legacy_record["path"] = LEGACY_CREDENTIAL_FILE
        records[legacy_record["id"]] = legacy_record

    env_credential = credential_from_environment()
    if env_credential is not None:
        env_record = account_record_from_credential(env_credential, name="Environment account", source="environment")
        records.setdefault(env_record["id"], env_record)

    return sorted(records.values(), key=lambda record: record["name"].lower())


def active_account_id() -> str | None:
    data = read_json(ACTIVE_ACCOUNT_FILE, {})
    if isinstance(data, dict) and data.get("id"):
        return str(data["id"])
    return None


def active_account_record() -> dict[str, Any] | None:
    records = load_account_records()
    if not records:
        return None

    active_id = active_account_id()
    if active_id:
        for record in records:
            if record["id"] == active_id:
                return record

    cached_records = [record for record in records if record.get("source") != "environment"]
    if len(cached_records) == 1:
        return cached_records[0]
    return None


def save_account_record(record: dict[str, Any], *, make_active: bool = True) -> None:
    account_id = str(record["id"])
    write_json(account_path(account_id), {key: value for key, value in record.items() if key != "path"})
    write_json(LEGACY_CREDENTIAL_FILE, record["credential"])
    if make_active:
        write_json(ACTIVE_ACCOUNT_FILE, {"id": account_id})


def credential_from_cache() -> Credential | None:
    record = active_account_record()
    if record is None:
        return None
    return credential_from_dict(record["credential"])


def save_credential(credential: Credential) -> None:
    record = account_record_from_credential(credential)
    save_account_record(record)


def credential_from_env() -> Credential | None:
    return credential_from_environment() or credential_from_cache()


def credential_for_requests() -> Credential | None:
    if USE_GUEST_MODE:
        return None
    return credential_from_env()


def request_delay_seconds() -> float:
    return 1.0 / REQUEST_FREQUENCY


async def close_bilibili_client() -> None:
    try:
        await get_client().close()
    except Exception:
        pass


def configure_bilibili_client() -> None:
    request_settings.set_timeout(20)
    request_settings.set("impersonate", "chrome120")
    request_settings.set("http2", False)


async def check_account_condition(
    credential: Credential | None,
) -> tuple[bool | None, str | None]:
    if credential is None or not credential.has_sessdata():
        return False, None

    configure_bilibili_client()
    try:
        return await credential.check_valid(), None
    except Exception as exc:
        return None, str(exc)
    finally:
        await close_bilibili_client()


def account_condition_summary() -> str:
    if USE_GUEST_MODE:
        return "Guest mode"

    record = active_account_record()
    if record is not None:
        name = record.get("name") or record["id"]
        uid = record.get("uid")
        return f"{name} (UID {uid})" if uid else str(name)

    if credential_from_environment() is not None:
        return "Environment account"
    return "Not signed in"


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
    QRCODE_FILE.parent.mkdir(parents=True, exist_ok=True)
    login.get_qrcode_picture().to_file(str(QRCODE_FILE))

    print(f"The QR code has been saved to: {QRCODE_FILE}")
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


def first_video(videos: dict[str, Any]) -> dict[str, Any]:
    items = videos.get("list", {}).get("vlist", [])
    if not items:
        raise LookupError("No video found for the user.")
    return items[0]


async def fetch_latest_video_like(uid: int, credential: Credential | None) -> dict[str, Any]:
    uploader = user.User(uid, credential=credential)

    videos = await uploader.get_videos(pn=1, ps=1, order=user.VideoOrder.PUBDATE)
    item = first_video(videos)
    await asyncio.sleep(request_delay_seconds())

    info = await video.Video(bvid=item["bvid"], credential=credential).get_info()
    stat = info.get("stat", {})
    return {
        "title": info.get("title") or item.get("title"),
        "bvid": info.get("bvid") or item.get("bvid"),
        "aid": info.get("aid") or item.get("aid"),
        "pubdate": datetime.fromtimestamp(info["pubdate"]).isoformat(sep=" ") if info.get("pubdate") else None,
        "like": stat.get("like"),
        "view": stat.get("view"),
        "reply": stat.get("reply"),
        "favorite": stat.get("favorite"),
        "coin": stat.get("coin"),
        "share": stat.get("share"),
    }


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
                f"{COOKIE_FILE} and try again."
            ) from exc
        raise
    finally:
        await close_bilibili_client()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Get the like count of the latest video.")
    parser.add_argument(
        "--object-file",
        type=Path,
        default=UPS_FILE,
        help="JSON file containing the UP space URL. Default: %(default)s",
    )
    parser.add_argument("--uid", type=int, default=None, help="Directly specify the UP UID.")
    parser.add_argument("--login", action="store_true", help="Use QR code sign-in when no account cache is available.")
    parser.add_argument("--print-terminal-qrcode", action="store_true", help="Print the QR code in the terminal.")
    return parser.parse_args()


def use_service_without_sign_in() -> None:
    global USE_GUEST_MODE

    USE_GUEST_MODE = True
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
            write_json(ACTIVE_ACCOUNT_FILE, {"id": record["id"]})
            print(f"Selected account: {record['name']}.")
            return credential
        if error:
            print(f"Could not check this account: {error}")
        else:
            print("That cached account is no longer valid.")
        return None


def sign_in() -> None:
    global USE_GUEST_MODE

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
            USE_GUEST_MODE = False
        return
    if choice == "2":
        try:
            if asyncio.run(credential_from_qrcode(print_terminal_qrcode=True)):
                USE_GUEST_MODE = False
        except TimeoutError as exc:
            print(f"Sign-in failed: {exc}")
        except Exception as exc:
            print(f"Unexpected error during sign-in: {exc}")
        return
    if choice == "3":
        use_service_without_sign_in()
        return

    print("Invalid sign-in choice.")


def unlink_if_exists(path: Path) -> bool:
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        print(f"Could not remove {path}: {exc}")
        return False


def clear_active_account_cache() -> int:
    removed = 0
    record = active_account_record()
    if record is not None:
        path = record.get("path")
        if isinstance(path, Path) and path != LEGACY_CREDENTIAL_FILE:
            removed += int(unlink_if_exists(path))
    removed += int(unlink_if_exists(ACTIVE_ACCOUNT_FILE))
    return removed


def clear_all_account_caches() -> int:
    removed = 0
    if ACCOUNTS_DIR.exists():
        for path in ACCOUNTS_DIR.glob("*.json"):
            removed += int(unlink_if_exists(path))
    for path in (ACTIVE_ACCOUNT_FILE, LEGACY_CREDENTIAL_FILE, COOKIE_FILE, QRCODE_FILE):
        removed += int(unlink_if_exists(path))
    return removed


def sign_out() -> None:
    if USE_GUEST_MODE:
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
        unlink_if_exists(ACTIVE_ACCOUNT_FILE)
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


async def load_account_detail(
    credential: Credential | None,
) -> tuple[bool | None, dict[str, Any] | None, str | None]:
    if credential is None or not credential.has_sessdata():
        return False, None, "No sign-in credential is available."

    configure_bilibili_client()
    try:
        if not await credential.check_valid():
            return False, None, None
        return True, await user.get_self_info(credential), None
    except Exception as exc:
        return None, None, str(exc)
    finally:
        await close_bilibili_client()


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


def view_account_detail() -> None:
    if USE_GUEST_MODE:
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


def select_an_up() -> None:
    entries = load_ups()

    while True:
        print("Select UP:")
        print("1. Choose from available UPs")
        print("2. Search UPs")
        print("3. Add a new UP")
        print(f"4. Show UP storage file path ({UPS_FILE})")
        print("0. Return to the menu")
        choice = input("-> ").strip()

        if choice == "0" or choice == "":
            print("UP selection canceled.")
            return
        if choice == "1":
            chosen = choose_from_list(entries)
            if chosen is not None:
                save_selected_up(chosen)
                print(f"Selected UP: {chosen['name']}.")
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
                print(f"Selected UP: {chosen['name']}.")
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
            print(f"Added and selected UP: {normalized['name']}.")
            return
        if choice == "4":
            print(f"UP list file: {UPS_FILE}")
            continue

        print("Invalid selection.")


def set_request_frequency() -> None:
    global REQUEST_FREQUENCY

    print(f"Current request frequency: {REQUEST_FREQUENCY:g} request(s) per second.")
    print(f"1. Reset to the default ({DEFAULT_REQUEST_FREQUENCY:g} request(s) per second)")
    print("2. Enter a custom request frequency")
    print("0. Return to the menu")
    choice = input("-> ").strip()

    if choice == "0" or choice == "":
        print("Request frequency was not changed.")
        return
    if choice == "1":
        REQUEST_FREQUENCY = DEFAULT_REQUEST_FREQUENCY
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
        REQUEST_FREQUENCY = new_frequency
    else:
        print("Invalid selection.")
        return

    print(
        f"Request frequency set to {REQUEST_FREQUENCY:g} request(s) per second "
        f"({request_delay_seconds():.3f} second delay)."
    )


def video_total_from_response(videos: dict[str, Any]) -> int:
    page = videos.get("page", {})
    for key in ("count", "total"):
        try:
            return int(page[key])
        except (KeyError, TypeError, ValueError):
            continue
    return len(videos.get("list", {}).get("vlist", []))


def prompt_video_count(total: int) -> int | None:
    print(f"Total videos released by this UP: {total}")
    print("Enter the number of videos to list.")
    print("0. Return to the menu")
    while True:
        count_input = input(f"1-{total}: ").strip()
        if count_input == "0" or count_input == "":
            print("Video listing canceled.")
            return None
        try:
            count = int(count_input)
        except ValueError:
            print("Enter a number.")
            continue
        if 1 <= count <= total:
            return count
        print(f"Enter a number from 1 to {total}.")


def format_count(value: Any) -> str:
    if value in (None, ""):
        return "Unknown"
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


async def fetch_selected_up_details() -> tuple[dict[str, Any] | None, str | None]:
    selected_up = load_selected_up()
    if selected_up is None:
        return None, "No UP is selected."

    uid = uid_from_up(selected_up)
    credential = credential_for_requests()
    uploader = user.User(uid, credential=credential)

    configure_bilibili_client()
    try:
        info = await uploader.get_user_info()
        relation = await uploader.get_relation_info()
        first_page = await uploader.get_videos(pn=1, ps=1, order=user.VideoOrder.PUBDATE)
        details: dict[str, Any] = {
            "selected": selected_up,
            "profile": info,
            "relation": relation,
            "video_total": video_total_from_response(first_page),
            "fetched_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
        }

        if credential is not None and credential.has_bili_jct():
            try:
                details["up_stat"] = await uploader.get_up_stat()
            except Exception as exc:
                details["up_stat_error"] = str(exc)
        return details, None
    except Exception as exc:
        return None, str(exc)
    finally:
        await close_bilibili_client()


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
    print(f"Details JSON: {UPS_FILE}")


def view_selected_up_account_details() -> None:
    details, error = asyncio.run(fetch_selected_up_details())
    if error:
        print(f"Could not load selected UP details: {error}")
        return
    if details is None:
        print("No selected UP details were returned.")
        return

    save_selected_up_details(details)
    print_selected_up_details(details)


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

        requested_count = prompt_video_count(total)
        if requested_count is None:
            return

        page_size = 30
        fetched_items: list[dict[str, Any]] = []
        page_number = 1

        while len(fetched_items) < requested_count:
            try:
                page_data = await uploader.get_videos(pn=page_number, ps=page_size, order=user.VideoOrder.PUBDATE)
            except Exception as exc:
                print(f"Failed to fetch video page {page_number}: {exc}")
                break

            page_items = page_data.get("list", {}).get("vlist", [])
            if not page_items:
                break

            fetched_items.extend(page_items[: requested_count - len(fetched_items)])
            page_number += 1
            await asyncio.sleep(request_delay_seconds())

        if not fetched_items:
            print("No videos were returned for this UP.")
            return
        if len(fetched_items) < requested_count:
            print(f"Only {len(fetched_items)} video(s) were returned by Bilibili.")

        for index, item in enumerate(fetched_items, start=1):
            title = item.get("title") or "(no title)"
            bvid = item.get("bvid")
            aid = item.get("aid")
            pub_ts = item.get("created") or item.get("pubdate")
            try:
                pubdate = datetime.fromtimestamp(int(pub_ts)).isoformat(sep=" ") if pub_ts else "Unknown"
            except Exception:
                pubdate = str(pub_ts)

            print(f"{index}. {title}")
            print(f"   BVID: {bvid}  AID: {aid}  Published: {pubdate}")

            if bvid:
                try:
                    info = await video.Video(bvid=bvid, credential=credential).get_info()
                    stat = info.get("stat", {})
                    print(
                        f"   Views: {stat.get('view')}  Likes: {stat.get('like')}  Replies: {stat.get('reply')}  "
                        f"Favorites: {stat.get('favorite')}  Coins: {stat.get('coin')}  Shares: {stat.get('share')}"
                    )
                except Exception as exc:
                    print(f"   (Failed to fetch video details: {exc})")
            else:
                print("   (No BVID available, skipping details)")

            await asyncio.sleep(request_delay_seconds())

    async def fetch_and_close() -> None:
        configure_bilibili_client()
        try:
            await fetch_and_print()
        finally:
            await close_bilibili_client()

    asyncio.run(fetch_and_close())


def print_main_menu() -> None:
    print("")
    print("Menu")
    print(f"Account: {account_condition_summary()}")
    print(f"Selected UP: {selected_up_summary()}")
    print(f"Request frequency: {REQUEST_FREQUENCY:g} request(s) per second")
    print("1. Sign in")
    print("2. Sign out")
    print("3. View account details")
    print("4. Set request frequency")
    print("5. Select an UP")
    print("6. View the selected UP's account details")
    print("7. Get the video list")
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
        elif choice == "0":
            break
        else:
            print("Invalid menu choice.")


if __name__ == "__main__":
    run_menu()
