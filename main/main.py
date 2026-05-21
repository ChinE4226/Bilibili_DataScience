import argparse
import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from bilibili_api import Credential, get_client, request_settings, user, video
from bilibili_api.exceptions import NetworkException
from bilibili_api.login_v2 import QrCodeLogin, QrCodeLoginEvents


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OBJECT_FILE = PROJECT_ROOT / "objects" / "Geekerwan.json"
QRCODE_FILE = PROJECT_ROOT / ".runtime" / "bilibili_qrcode.png"
COOKIE_FILE = PROJECT_ROOT / ".runtime" / "bilibili_cookie.txt"
CREDENTIAL_FILE = PROJECT_ROOT / ".runtime" / "bilibili_credential.json"
LOCAL_SIGN_IN_CACHE_FILES = (CREDENTIAL_FILE, COOKIE_FILE, QRCODE_FILE)
DEFAULT_REQUEST_FREQUENCY = 4.0
REQUEST_FREQUENCY = DEFAULT_REQUEST_FREQUENCY
USE_GUEST_MODE = False


def load_uid(object_file: Path) -> int:
    data = json.loads(object_file.read_text(encoding="utf-8"))
    space = data["space"]
    match = re.search(r"space\.bilibili\.com/(\d+)", space)
    if not match:
        raise ValueError(f"Cannot parse Bilibili uid from {space!r}")
    return int(match.group(1))


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
    cookies = parse_cookie_header(cookie_header)
    return Credential(
        sessdata=cookies.get("SESSDATA"),
        bili_jct=cookies.get("bili_jct"),
        dedeuserid=cookies.get("DedeUserID"),
        buvid3=cookies.get("buvid3"),
        buvid4=cookies.get("buvid4"),
        ac_time_value=cookies.get("ac_time_value"),
    )


def credential_to_dict(credential: Credential) -> dict[str, str | None]:
    return {
        "sessdata": credential.sessdata,
        "bili_jct": credential.bili_jct,
        "dedeuserid": credential.dedeuserid,
        "buvid3": credential.buvid3,
        "buvid4": credential.buvid4,
        "ac_time_value": credential.ac_time_value,
    }


def credential_from_cache() -> Credential | None:
    if not CREDENTIAL_FILE.exists():
        return None
    try:
        data = json.loads(CREDENTIAL_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Cannot read the credential cache: {exc}")
        return None
    return Credential(**data)


def save_credential(credential: Credential) -> None:
    CREDENTIAL_FILE.parent.mkdir(parents=True, exist_ok=True)
    CREDENTIAL_FILE.write_text(
        json.dumps(credential_to_dict(credential), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def credential_from_env() -> Credential | None:
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
        return credential_from_cache()

    return Credential(
        sessdata=sessdata,
        bili_jct=bili_jct,
        dedeuserid=dedeuserid,
        buvid3=buvid3,
        buvid4=buvid4,
        ac_time_value=ac_time_value,
    )


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


async def credential_from_qrcode(print_terminal_qrcode: bool = False) -> Credential:
    login = QrCodeLogin()
    await login.generate_qrcode()
    QRCODE_FILE.parent.mkdir(parents=True, exist_ok=True)
    login.get_qrcode_picture().to_file(str(QRCODE_FILE))

    print(f"The QR code has been saved to: {QRCODE_FILE}")
    if print_terminal_qrcode:
        print(login.get_qrcode_terminal())
    print("Scan the QR code with the signed-in Bilibili app to finish sign-in.")

    try:
        while True:
            event = await login.check_state()
            if event == QrCodeLoginEvents.DONE:
                save_credential(login.get_credential())
                print("Sign-in successful. The credential was cached.")
                return login.get_credential()
            if event == QrCodeLoginEvents.TIMEOUT:
                raise TimeoutError("The QR code has expired. Run sign-in again.")
            await asyncio.sleep(2)
    finally:
        await close_bilibili_client()


def configure_bilibili_client() -> None:
    request_settings.set_timeout(20)
    request_settings.set("impersonate", "chrome120")
    request_settings.set("http2", False)


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
        "pubdate": datetime.fromtimestamp(info["pubdate"]).isoformat(sep=" ")
        if info.get("pubdate")
        else None,
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
                "Bilibili returned 412. Please use --login to scan the QR code, or save the entire Cookie from bilibili.com in your browser to "
                f"{COOKIE_FILE} and try again. The script will cache the credentials to {CREDENTIAL_FILE} after a successful scan."
            ) from exc
        raise
    finally:
        await close_bilibili_client()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Get the like count of the latest video."
    )
    parser.add_argument(
        "--object-file",
        type=Path,
        default=DEFAULT_OBJECT_FILE,
        help="The JSON file containing the UP's space URL. Default: %(default)s",
    )
    parser.add_argument("--uid", type=int, default=None, help="Directly specify the UP's UID.")
    parser.add_argument(
        "--login",
        action="store_true",
        help="Use QR code login when no cookie is provided in environment variables.",
    )
    parser.add_argument(
        "--print-terminal-qrcode",
        action="store_true",
        help="Print the QR code in the terminal; by default, only saves the PNG file.",
    )
    return parser.parse_args()


def use_service_without_sign_in() -> None:
    global USE_GUEST_MODE

    USE_GUEST_MODE = True
    print("Guest mode enabled. Public requests will run without a signed-in account.")


def sign_in() -> None:
    """Choose a signed-in account or guest mode for this run."""
    global USE_GUEST_MODE

    print("Sign-in options:")
    print("1. Use a cached account or sign in with a QR code")
    print("0. Use the service without signing in")
    print("q. Return to the menu")
    choice = input("-> ").strip().lower()

    if choice == "0":
        use_service_without_sign_in()
        return
    if choice in {"", "q"}:
        print("Sign-in canceled.")
        return
    if choice != "1":
        print("Invalid sign-in choice.")
        return

    credential = credential_from_env()
    is_valid, error = asyncio.run(check_account_condition(credential))
    if is_valid:
        USE_GUEST_MODE = False
        print("A valid cached credential is available. No QR scan is needed.")
        return
    if error:
        print(f"Could not check the cached account: {error}")
    elif credential is not None:
        print("The cached credential is no longer valid.")
    else:
        print("No cached sign-in credential is available.")

    try:
        credential = asyncio.run(credential_from_qrcode())
        if credential:
            USE_GUEST_MODE = False
    except TimeoutError as exc:
        print(f"Sign-in failed: {exc}")
    except Exception as exc:
        print(f"Unexpected error during sign-in: {exc}")


def clear_local_sign_in_cache() -> list[Path]:
    cleared_files: list[Path] = []
    for cache_file in LOCAL_SIGN_IN_CACHE_FILES:
        try:
            cache_file.unlink()
        except FileNotFoundError:
            continue
        except OSError as exc:
            print(f"Could not remove {cache_file}: {exc}")
        else:
            cleared_files.append(cache_file)
    return cleared_files


def sign_out() -> None:
    """Switch to guest mode and optionally delete local sign-in files."""
    credential = credential_for_requests()
    is_valid, error = asyncio.run(check_account_condition(credential))

    if is_valid:
        print("The account credential currently in use is valid.")
    elif error:
        print(f"Could not check the account credential currently in use: {error}")
    else:
        print("No valid signed-in account is currently in use.")

    clear_choice = input("Clear the local sign-in cache? [y/N]: ").strip().lower()
    if clear_choice == "y":
        cleared_files = clear_local_sign_in_cache()
        if cleared_files:
            print(f"Cleared {len(cleared_files)} local sign-in cache file(s).")
        else:
            print("No local sign-in cache files were found.")
        if os.getenv("BILI_COOKIE") or os.getenv("BILI_SESSDATA"):
            print("Credentials from environment variables were not cleared.")
    else:
        print("Local sign-in cache kept. Choose sign in later to reuse a valid cache without scanning a QR code.")

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


def select_an_up():
    """Allow the user to list, search, add and select an UP (uploader).

    - Reads any existing UP list from main/obejects.json or the default object file.
    - Lets the user add a new UP by name and space URL (validates the URL).
    - Saves the chosen UP to DEFAULT_OBJECT_FILE so other parts of the script can use it.
    """
    configure_bilibili_client()

    # Candidate list sources
    candidate_list_file = PROJECT_ROOT / "main" / "obejects.json"
    candidates: list[dict[str, str]] = []

    # Try reading the main/obejects.json (tolerant to small formatting issues)
    if candidate_list_file.exists():
        raw = candidate_list_file.read_text(encoding="utf-8")
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                candidates = parsed
            elif isinstance(parsed, dict):
                candidates = [parsed]
        except Exception:
            # fallback: extract simple { "name": "..", "space": ".." } patterns
            pattern = r'\{\s*"name"\s*:\s*"([^\"]+)"\s*,\s*"space"\s*:\s*"([^\"]+)"\s*\}'
            found = re.findall(pattern, raw)
            candidates = [{"name": m[0], "space": m[1]} for m in found]

    # Also include DEFAULT_OBJECT_FILE if present
    if DEFAULT_OBJECT_FILE.exists():
        try:
            d = json.loads(DEFAULT_OBJECT_FILE.read_text(encoding="utf-8"))
            if isinstance(d, dict) and d.get("space"):
                # put default at top if not duplicate
                if not any(c.get("space") == d.get("space") for c in candidates):
                    candidates.insert(0, d)
        except Exception:
            pass

    def print_candidates():
        if not candidates:
            print("No UPs found in objects. You can add one.")
            return
        print("Available UPs:")
        for i, c in enumerate(candidates, start=1):
            print(f"{i}. {c.get('name')!s} - {c.get('space')!s}")

    while True:
        print_candidates()
        choice = input("Select by number, (a)dd new, (s)earch, or (q)uit: ").strip().lower()
        if choice == "q":
            print("Cancel.")
            return
        if choice == "a":
            name = input("Enter UP display name: ").strip()
            space = input("Enter space URL (e.g. https://space.bilibili.com/12345): ").strip()
            # validate and normalize
            m = re.search(r"space\.bilibili\.com/(\d+)", space)
            if not m:
                print("Cannot parse UID from the provided URL. Aborting add.")
                continue
            entry = {"name": name or f"UP-{m.group(1)}", "space": space}
            candidates.append(entry)
            # persist to candidate_list_file if possible, else save to DEFAULT_OBJECT_FILE's dir
            try:
                # if the original list file existed and parsed to a list, append there
                if candidate_list_file.exists():
                    try:
                        orig = json.loads(candidate_list_file.read_text(encoding="utf-8"))
                        if isinstance(orig, list):
                            orig.append(entry)
                            candidate_list_file.write_text(json.dumps(orig, ensure_ascii=False, indent=2), encoding="utf-8")
                            print(f"Added to {candidate_list_file}")
                            continue
                    except Exception:
                        pass
                # fallback: write/update DEFAULT_OBJECT_FILE.parent/objects.json
                target = DEFAULT_OBJECT_FILE.parent / "objects.json"
                target.parent.mkdir(parents=True, exist_ok=True)
                arr = []
                if target.exists():
                    try:
                        arr = json.loads(target.read_text(encoding="utf-8"))
                        if not isinstance(arr, list):
                            arr = []
                    except Exception:
                        arr = []
                arr.append(entry)
                target.write_text(json.dumps(arr, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"Added and saved to {target}")
            except Exception as exc:
                print(f"Failed to save new UP: {exc}")
            continue

        if choice == "s":
            query = input("Search by name or UID: ").strip().lower()
            if not query:
                continue
            results = []
            for c in candidates:
                if query in (c.get("name") or "").lower() or query in (c.get("space") or ""):
                    results.append(c)
                else:
                    m = re.search(r"space\.bilibili\.com/(\d+)", c.get("space", ""))
                    if m and query == m.group(1):
                        results.append(c)
            if not results:
                print("No results.")
                continue
            for i, c in enumerate(results, start=1):
                print(f"{i}. {c.get('name')} - {c.get('space')}")
            sel = input("Select a result number to choose, or Enter to return: ").strip()
            if not sel:
                continue
            try:
                idx = int(sel) - 1
                chosen = results[idx]
            except Exception:
                print("Invalid selection.")
                continue
            # persist chosen
            DEFAULT_OBJECT_FILE.parent.mkdir(parents=True, exist_ok=True)
            DEFAULT_OBJECT_FILE.write_text(json.dumps(chosen, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Selected {chosen.get('name')} and saved to {DEFAULT_OBJECT_FILE}")
            return

        # try numeric selection
        try:
            idx = int(choice) - 1
            if idx < 0 or idx >= len(candidates):
                print("Invalid index.")
                continue
            chosen = candidates[idx]
            DEFAULT_OBJECT_FILE.parent.mkdir(parents=True, exist_ok=True)
            DEFAULT_OBJECT_FILE.write_text(json.dumps(chosen, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Selected {chosen.get('name')} and saved to {DEFAULT_OBJECT_FILE}")
            return
        except ValueError:
            print("Unknown command.")
            continue


def set_request_frequency() -> None:
    """Set the request pacing for video-detail fetches in this run."""
    global REQUEST_FREQUENCY

    print(f"Current request frequency: {REQUEST_FREQUENCY:g} request(s) per second.")
    frequency_input = input(
        f"New request frequency in requests per second [{DEFAULT_REQUEST_FREQUENCY:g}]: "
    ).strip()

    if not frequency_input:
        REQUEST_FREQUENCY = DEFAULT_REQUEST_FREQUENCY
    else:
        try:
            new_frequency = float(frequency_input)
        except ValueError:
            print("Request frequency must be a number.")
            return
        if new_frequency <= 0:
            print("Request frequency must be greater than 0.")
            return
        REQUEST_FREQUENCY = new_frequency

    print(
        f"Request frequency set to {REQUEST_FREQUENCY:g} request(s) per second "
        f"({request_delay_seconds():.3f} second delay)."
    )


def get_video_list():
    """Fetch and print the UP's video list with details to the terminal."""
    configure_bilibili_client()

    if not DEFAULT_OBJECT_FILE.exists():
        print(f"Default object file not found at {DEFAULT_OBJECT_FILE}. Use select_an_up() to choose an UP first.")
        return

    try:
        uid = load_uid(DEFAULT_OBJECT_FILE)
    except Exception as exc:
        print(f"Failed to load UID from {DEFAULT_OBJECT_FILE}: {exc}")
        return

    credential = credential_for_requests()

    count_input = input("How many videos to list? [20]: ").strip()
    try:
        ps = int(count_input) if count_input else 20
    except Exception:
        ps = 20

    async def _fetch_and_print():
        uploader = user.User(uid, credential=credential)
        try:
            videos = await uploader.get_videos(pn=1, ps=ps, order=user.VideoOrder.PUBDATE)
        except Exception as exc:
            print(f"Failed to fetch video list: {exc}")
            return

        vlist = videos.get("list", {}).get("vlist", [])
        if not vlist:
            print("No videos found for this UP.")
            return

        for i, item in enumerate(vlist, start=1):
            title = item.get("title") or "(no title)"
            bvid = item.get("bvid")
            aid = item.get("aid")
            # created or pubdate sometimes used
            pub_ts = item.get("created") or item.get("pubdate")
            try:
                pubdate = datetime.fromtimestamp(int(pub_ts)).isoformat(sep=" ") if pub_ts else "Unknown"
            except Exception:
                pubdate = str(pub_ts)

            print(f"{i}. {title}")
            print(f"   BVID: {bvid}  AID: {aid}  Published: {pubdate}")

            # Try to fetch detailed info/stats for each video
            if bvid:
                try:
                    info = await video.Video(bvid=bvid, credential=credential).get_info()
                    stat = info.get("stat", {})
                    print(
                        f"   Views: {stat.get('view')}  Likes: {stat.get('like')}  Replies: {stat.get('reply')}  "
                        f"Favorites: {stat.get('favorite')}  Coins: {stat.get('coin')}  Shares: {stat.get('share')}")
                except Exception as exc:
                    print(f"   (Failed to fetch video details: {exc})")
            else:
                print("   (No BVID available, skipping details)")

            await asyncio.sleep(request_delay_seconds())

    async def _fetch_and_close():
        try:
            await _fetch_and_print()
        finally:
            await close_bilibili_client()

    asyncio.run(_fetch_and_close())


if __name__ == "__main__":
    while True:
        print("")
        print("Menu")
        print("1. sign in")
        print("2. sign out")
        print("3. view account details")
        print("4. select an UP")
        print("5. set request frequency")
        print("6. get the video list")
        print("0. exit")
        choice = input("-> ")

        if choice == "1":
            sign_in()

        elif choice == "2":
            sign_out()

        elif choice == "3":
            view_account_detail()

        elif choice == "4":
            select_an_up()

        elif choice == "5":
            set_request_frequency()

        elif choice == "6":
            get_video_list()

        elif choice == "0":
            break

        else:
            print("Invalid menu choice.")
