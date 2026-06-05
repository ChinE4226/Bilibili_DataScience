import argparse
import asyncio
import hashlib
import json
import os
import re
import statistics
import qrcode

from datetime import datetime
from pathlib import Path
from typing import Any
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
PLOTS_DIR = RUNTIME_DIR / "plots"

os.environ.setdefault("MPLCONFIGDIR", str(RUNTIME_DIR / "matplotlib"))
os.environ.setdefault("XDG_CACHE_HOME", str(RUNTIME_DIR / "cache"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

DEFAULT_REQUEST_FREQUENCY = 4.0
REQUEST_FREQUENCY = DEFAULT_REQUEST_FREQUENCY
USE_GUEST_MODE = False
SELECTED_UID: str | None = None

VIDEO_STAT_FIELDS = [
    ("views", "Views", "view"),
    ("likes", "Likes", "like"),
    ("replies", "Replies", "reply"),
    ("favorites", "Favorites", "favorite"),
    ("coins", "Coins", "coin"),
    ("shares", "Shares", "share"),
]


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
    if isinstance(data, dict) and isinstance(data.get("ups"), list):
        if object_file.resolve() == UPS_FILE.resolve():
            selected_up = load_selected_up()
            if selected_up is not None:
                return uid_from_up(selected_up)
        ups = normalize_up_entries(data.get("ups", []))
        if ups:
            return uid_from_up(ups[0])
    if isinstance(data, list):
        ups = normalize_up_entries(data)
        if ups:
            return uid_from_up(ups[0])
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
    return {"ups": []}


def load_up_store() -> dict[str, Any]:
    global SELECTED_UID

    raw = read_json(UPS_FILE, default_up_store())
    if isinstance(raw, list):
        store = {"ups": normalize_up_entries(raw)}
    elif isinstance(raw, dict):
        if SELECTED_UID is None and raw.get("selected_uid"):
            SELECTED_UID = str(raw["selected_uid"])
        store = {"ups": normalize_up_entries(raw.get("ups", []))}
    else:
        store = default_up_store()

    store["ups"] = merge_up_entries(store["ups"])
    known_uids = {entry["uid"] for entry in store["ups"]}
    if SELECTED_UID not in known_uids:
        SELECTED_UID = store["ups"][0]["uid"] if store["ups"] else None
    write_json(UPS_FILE, store)
    return store


def save_up_store(store: dict[str, Any]) -> None:
    global SELECTED_UID

    normalized_store = {"ups": merge_up_entries(normalize_up_entries(store.get("ups", [])))}
    known_uids = {entry["uid"] for entry in normalized_store["ups"]}
    if SELECTED_UID not in known_uids:
        SELECTED_UID = normalized_store["ups"][0]["uid"] if normalized_store["ups"] else None
    write_json(UPS_FILE, normalized_store)


def load_ups() -> list[dict[str, str]]:
    return load_up_store()["ups"]


def save_ups(entries: list[dict[str, str]]) -> None:
    store = load_up_store()
    store["ups"] = merge_up_entries(entries)
    save_up_store(store)


def load_selected_up() -> dict[str, str] | None:
    store = load_up_store()
    for entry in store["ups"]:
        if entry["uid"] == SELECTED_UID:
            return entry
    return None


def save_selected_up(entry: dict[str, str]) -> None:
    global SELECTED_UID

    normalized = normalize_up(entry)
    if normalized is None:
        raise ValueError("Cannot save an invalid UP entry.")
    store = load_up_store()
    store["ups"] = merge_up_entries([*store["ups"], normalized])
    SELECTED_UID = normalized["uid"]
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


def video_sort_mode(field_key: str, field_label: str, stat_key: str | None, descending: bool) -> dict[str, Any]:
    direction_label = (
        "latest to oldest"
        if field_key == "published_time" and descending
        else "oldest to latest"
        if field_key == "published_time"
        else "largest to smallest"
        if descending
        else "smallest to largest"
    )
    return {
        "field": field_key,
        "label": f"{field_label} ({direction_label})",
        "stat_key": stat_key,
        "descending": descending,
    }


def video_selection_choices() -> list[dict[str, Any]]:
    choices: list[dict[str, Any]] = [
        {
            "kind": "published_time_range",
            "label": "Published time (latest to oldest)",
            "sort_mode": video_sort_mode("published_time", "Published time", None, True),
        },
        {
            "kind": "published_time_range",
            "label": "Published time (oldest to latest)",
            "sort_mode": video_sort_mode("published_time", "Published time", None, False),
        },
    ]

    for field_key, field_label, stat_key in VIDEO_STAT_FIELDS:
        choices.append(
            {
                "kind": "metric_range",
                "field": field_key,
                "label": f"{field_label} (smallest to largest)",
                "range_label": field_label,
                "stat_key": stat_key,
                "sort_mode": video_sort_mode(field_key, field_label, stat_key, False),
            }
        )

    choices.append(
        {
            "kind": "published_time_position_range",
            "label": "Published-time ordered number range (latest to oldest)",
        }
    )
    return choices


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


def parse_datetime_input(raw: str, *, end_of_day: bool = False) -> datetime | None:
    value = raw.strip()
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) and end_of_day:
        return parsed.replace(hour=23, minute=59, second=59)
    return parsed


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


def parse_int_range_value(raw: str) -> int | None:
    value = raw.strip().lower().replace(",", "").replace(" ", "")
    if not value:
        return None
    multiplier = 1
    if value.endswith("k"):
        multiplier = 1_000
        value = value[:-1]
    elif value.endswith("m"):
        multiplier = 1_000_000
        value = value[:-1]

    try:
        number = float(value)
    except ValueError:
        return None
    if number < 0:
        return None
    return int(number * multiplier)


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


def format_count(value: Any) -> str:
    if value in (None, ""):
        return "Unknown"
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


def int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def video_published_timestamp(item: dict[str, Any]) -> int | None:
    return int_or_none(item.get("pubdate") or item.get("created"))


def video_sort_value(item: dict[str, Any], sort_mode: dict[str, Any]) -> int | None:
    if sort_mode["field"] == "published_time":
        return video_published_timestamp(item)
    stat = item.get("stat") if isinstance(item.get("stat"), dict) else {}
    return int_or_none(stat.get(sort_mode["stat_key"]))


def sort_video_items(items: list[dict[str, Any]], sort_mode: dict[str, Any]) -> list[dict[str, Any]]:
    direction = -1 if sort_mode["descending"] else 1

    def sort_key(item: dict[str, Any]) -> tuple[int, int]:
        value = video_sort_value(item, sort_mode)
        if value is None:
            return (1, 0)
        return (0, direction * value)

    return sorted(items, key=sort_key)


def format_video_published_time(item: dict[str, Any]) -> str:
    timestamp = video_published_timestamp(item)
    if timestamp is None:
        return "Unknown"
    try:
        return datetime.fromtimestamp(timestamp).isoformat(sep=" ")
    except Exception:
        return str(timestamp)


def print_video_entry(index: int, item: dict[str, Any]) -> None:
    title = item.get("title") or "(no title)"
    bvid = item.get("bvid")
    aid = item.get("aid")
    stat = item.get("stat") if isinstance(item.get("stat"), dict) else {}

    print(f"{index}. {title}")
    print(f"   BVID: {bvid}  AID: {aid}  Published time: {format_video_published_time(item)}")
    print(
        f"   Views: {format_count(stat.get('view'))}  Likes: {format_count(stat.get('like'))}  "
        f"Replies: {format_count(stat.get('reply'))}  Favorites: {format_count(stat.get('favorite'))}  "
        f"Coins: {format_count(stat.get('coin'))}  Shares: {format_count(stat.get('share'))}"
    )
    if item.get("detail_error"):
        print(f"   (Failed to fetch video details: {item['detail_error']})")


def video_metric_value(item: dict[str, Any], stat_key: str) -> int | None:
    stat = item.get("stat") if isinstance(item.get("stat"), dict) else {}
    return int_or_none(stat.get(stat_key))


def format_analysis_number(value: float | int | None) -> str:
    if value is None:
        return "Unknown"
    if isinstance(value, float) and not value.is_integer():
        return f"{value:,.2f}"
    return f"{int(value):,}"


def calculate_metric_summary(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    for _, label, stat_key in VIDEO_STAT_FIELDS:
        values = [
            value
            for item in items
            if stat_key is not None
            if (value := video_metric_value(item, stat_key)) is not None
        ]
        summaries.append(
            {
                "label": label,
                "count": len(values),
                "mean": statistics.mean(values) if values else None,
                "median": statistics.median(values) if values else None,
            }
        )
    return summaries


def print_analysis_result(
    *,
    selected_up: dict[str, str],
    selection_label: str,
    items: list[dict[str, Any]],
) -> None:
    print("Analysis result")
    print(f"UP: {selected_up['name']} (UID {selected_up['uid']})")
    print(f"Selection: {selection_label}")
    print(f"Selected videos: {len(items)}")

    summaries = calculate_metric_summary(items)
    print("")
    print(f"{'Metric':<12}{'Data count':>12}{'Mean':>18}{'Median':>18}")
    for summary in summaries:
        print(
            f"{summary['label']:<12}"
            f"{summary['count']:>12}"
            f"{format_analysis_number(summary['mean']):>18}"
            f"{format_analysis_number(summary['median']):>18}"
        )


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


def division_field_choices() -> list[dict[str, str]]:
    choices = [
        {
            "field": field_key,
            "label": label,
            "source": "video_stat",
            "stat_key": stat_key,
        }
        for field_key, label, stat_key in VIDEO_STAT_FIELDS
    ]
    choices.append(
        {
            "field": "followers",
            "label": "Followers",
            "source": "up_relation",
            "relation_key": "follower",
        }
    )
    return choices


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


def division_needs_up_relation(*fields: dict[str, str]) -> bool:
    return any(field.get("source") == "up_relation" for field in fields)


def division_field_value(
    item: dict[str, Any],
    field: dict[str, str],
    up_relation: dict[str, Any] | None = None,
) -> int | None:
    if field.get("source") == "up_relation":
        return int_or_none((up_relation or {}).get(field["relation_key"]))
    return video_metric_value(item, field["stat_key"])


def ratio_for_item(
    item: dict[str, Any],
    numerator_field: dict[str, str],
    denominator_field: dict[str, str],
    up_relation: dict[str, Any] | None = None,
) -> tuple[int | None, int | None, float | None]:
    numerator = division_field_value(item, numerator_field, up_relation)
    denominator = division_field_value(item, denominator_field, up_relation)
    if numerator is None or denominator in (None, 0):
        return numerator, denominator, None
    return numerator, denominator, numerator / denominator


def format_ratio(value: float | None) -> str:
    if value is None:
        return "Undefined"
    return f"{value:,.6f} ({value * 100:,.2f}%)"


def print_single_video_division_result(
    items: list[dict[str, Any]],
    numerator_field: dict[str, str],
    denominator_field: dict[str, str],
    selection_label: str,
    up_relation: dict[str, Any] | None = None,
) -> None:
    print("Division result for every selected video")
    print(f"Selection: {selection_label}")
    print(f"Ratio: {numerator_field['label']} / {denominator_field['label']}")
    print(f"Selected videos: {len(items)}")

    skipped = 0
    for index, item in enumerate(items, start=1):
        numerator, denominator, ratio = ratio_for_item(
            item,
            numerator_field,
            denominator_field,
            up_relation,
        )
        if ratio is None:
            skipped += 1
        title = item.get("title") or "(no title)"
        print(f"{index}. {title}")
        print(f"   Published time: {format_video_published_time(item)}")
        print(
            f"   {numerator_field['label']}: {format_count(numerator)}  "
            f"{denominator_field['label']}: {format_count(denominator)}  "
            f"Ratio: {format_ratio(ratio)}"
        )

    if skipped:
        print(f"Skipped ratio calculation for {skipped} video(s) with missing data or zero denominator.")


def aggregate_division_value(
    items: list[dict[str, Any]],
    field: dict[str, str],
    up_relation: dict[str, Any] | None = None,
) -> dict[str, int | None]:
    if field.get("source") == "up_relation":
        value = division_field_value({}, field, up_relation)
        selected_count = len(items)
        return {
            "value": None if value is None else value * selected_count,
            "count": selected_count if value is not None else 0,
            "missing": 0 if value is not None else selected_count,
            "base_value": value,
        }

    total = 0
    count = 0
    missing = 0
    for item in items:
        value = division_field_value(item, field, up_relation)
        if value is None:
            missing += 1
            continue
        total += value
        count += 1

    return {"value": total, "count": count, "missing": missing}


def aggregate_division_label(field: dict[str, str], selected_count: int | None = None) -> str:
    if field.get("source") == "up_relation":
        if selected_count is None:
            return field["label"]
        return f"{field['label']} x {selected_count} selected video(s)"
    return f"Total {field['label']}"


def print_aggregate_division_result(
    items: list[dict[str, Any]],
    numerator_field: dict[str, str],
    denominator_field: dict[str, str],
    selection_label: str,
    up_relation: dict[str, Any] | None = None,
) -> None:
    numerator_summary = aggregate_division_value(items, numerator_field, up_relation)
    denominator_summary = aggregate_division_value(items, denominator_field, up_relation)
    numerator_total = numerator_summary["value"]
    denominator_total = denominator_summary["value"]

    ratio = (
        None
        if numerator_total is None or denominator_total in (None, 0)
        else numerator_total / denominator_total
    )

    print("Division result for all selected videos")
    print(f"Selection: {selection_label}")
    selected_count = len(items)
    print(
        f"Ratio: {aggregate_division_label(numerator_field, selected_count)} / "
        f"{aggregate_division_label(denominator_field, selected_count)}"
    )
    print(f"Selected videos: {selected_count}")
    print(f"{aggregate_division_label(numerator_field, selected_count)}: {format_count(numerator_total)}")
    print(f"{aggregate_division_label(denominator_field, selected_count)}: {format_count(denominator_total)}")
    if numerator_summary["missing"] or denominator_summary["missing"]:
        print(
            "Missing data: "
            f"{numerator_field['label']} {numerator_summary['missing']}, "
            f"{denominator_field['label']} {denominator_summary['missing']}"
        )
    if division_needs_up_relation(numerator_field, denominator_field):
        print("Followers is multiplied by the selected video count in aggregate mode.")
    print(f"Ratio: {format_ratio(ratio)}")


async def fetch_video_summaries(
    uploader: Any,
    target_count: int,
    order: user.VideoOrder,
) -> list[dict[str, Any]]:
    page_size = 30
    fetched_items: list[dict[str, Any]] = []
    page_number = 1

    while len(fetched_items) < target_count:
        try:
            page_data = await uploader.get_videos(pn=page_number, ps=page_size, order=order)
        except Exception as exc:
            print(f"Failed to fetch video page {page_number}: {exc}")
            break

        page_items = page_data.get("list", {}).get("vlist", [])
        if not page_items:
            break

        fetched_items.extend(page_items[: target_count - len(fetched_items)])
        page_number += 1
        await asyncio.sleep(request_delay_seconds())

    return fetched_items


async def fetch_video_detail(item: dict[str, Any], credential: Credential | None) -> dict[str, Any]:
    enriched = dict(item)
    bvid = enriched.get("bvid")
    if not bvid:
        enriched["stat"] = {}
        enriched["detail_error"] = "No BVID available."
        return enriched

    try:
        info = await video.Video(bvid=bvid, credential=credential).get_info()
    except Exception as exc:
        enriched["stat"] = {}
        enriched["detail_error"] = str(exc)
        return enriched

    stat = info.get("stat") if isinstance(info.get("stat"), dict) else {}
    enriched.update(
        {
            "title": info.get("title") or enriched.get("title"),
            "bvid": info.get("bvid") or enriched.get("bvid"),
            "aid": info.get("aid") or enriched.get("aid"),
            "pubdate": info.get("pubdate") or enriched.get("pubdate") or enriched.get("created"),
            "stat": stat,
        }
    )
    return enriched


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


def view_selected_up_account_details() -> None:
    details, error = asyncio.run(fetch_selected_up_details())
    if error:
        print(f"Could not load selected UP details: {error}")
        return
    if details is None:
        print("No selected UP details were returned.")
        return

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


def filter_items_by_published_time_range(
    items: list[dict[str, Any]],
    start_timestamp: int,
    end_timestamp: int,
) -> list[dict[str, Any]]:
    return [
        item
        for item in items
        if (published_time := video_published_timestamp(item)) is not None
        if start_timestamp <= published_time <= end_timestamp
    ]


def filter_items_by_metric_range(
    items: list[dict[str, Any]],
    stat_key: str,
    minimum_value: int | None,
    maximum_value: int | None,
) -> list[dict[str, Any]]:
    return [
        item
        for item in items
        if (metric_value := video_metric_value(item, stat_key)) is not None
        if minimum_value is None or metric_value > minimum_value
        if maximum_value is None or metric_value < maximum_value
    ]


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
        for field_key, label, stat_key in VIDEO_STAT_FIELDS
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


def ordered_by_published_time(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sort_video_items(
        items,
        video_sort_mode("published_time", "Published time", None, False),
    )


def plot_file_path(selected_up: dict[str, str], plot_label: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_up_name = re.sub(r"[^\w.-]+", "_", selected_up.get("name", ""), flags=re.UNICODE).strip("_")[:40]
    up_part = f"{safe_up_name}_{selected_up['uid']}" if safe_up_name else selected_up["uid"]
    safe_label = re.sub(r"[^\w.-]+", "_", plot_label, flags=re.UNICODE).strip("_")[:80] or "plot"
    return PLOTS_DIR / f"{up_part}_{timestamp}_{safe_label}.png"


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
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = plot_file_path(selected_up, plot_label)

    figure, axis = plt.subplots(figsize=(12, 6))
    axis.plot(x_values, y_values, marker="o", linewidth=1.5, markersize=4)
    axis.set_title(f"{selected_up['name']} - {plot_label}")
    axis.set_xlabel("Published time")
    axis.set_ylabel(y_label)
    axis.grid(True, linewidth=0.4, alpha=0.45)
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


def print_plot_result(output_path: Path, plotted_count: int, skipped_count: int) -> None:
    print(f"Plotted points: {plotted_count}")
    if skipped_count:
        print(f"Skipped videos with missing published time, missing data, or zero denominator: {skipped_count}")
    print(f"Plot saved to: {output_path}")


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


if __name__ == "__main__":
    run_menu()
