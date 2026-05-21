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
REQUEST_DELAY_SECONDS = 1.5


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
    data = json.loads(CREDENTIAL_FILE.read_text(encoding="utf-8"))
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


async def credential_from_qrcode(print_terminal_qrcode: bool = False) -> Credential:
    login = QrCodeLogin()
    await login.generate_qrcode()
    QRCODE_FILE.parent.mkdir(parents=True, exist_ok=True)
    login.get_qrcode_picture().to_file(str(QRCODE_FILE))

    print(f"二维码图片已保存到：{QRCODE_FILE}")
    if print_terminal_qrcode:
        print(login.get_qrcode_terminal())
    print("请用已登录的哔哩哔哩 App 扫码并确认登录。")

    while True:
        event = await login.check_state()
        if event == QrCodeLoginEvents.DONE:
            save_credential(login.get_credential())
            print("扫码登录成功。")
            return login.get_credential()
        if event == QrCodeLoginEvents.TIMEOUT:
            raise TimeoutError("二维码已过期，请重新运行脚本。")
        await asyncio.sleep(2)


def configure_bilibili_client() -> None:
    request_settings.set_timeout(20)
    request_settings.set("impersonate", "chrome120")
    request_settings.set("http2", True)


def first_video(videos: dict[str, Any]) -> dict[str, Any]:
    items = videos.get("list", {}).get("vlist", [])
    if not items:
        raise LookupError("Geekerwan 投稿列表为空，无法获取最新视频。")
    return items[0]


async def fetch_latest_video_like(uid: int, credential: Credential | None) -> dict[str, Any]:
    uploader = user.User(uid, credential=credential)

    videos = await uploader.get_videos(pn=1, ps=1, order=user.VideoOrder.PUBDATE)
    item = first_video(videos)

    await asyncio.sleep(REQUEST_DELAY_SECONDS)

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
        if "状态码：412" in message or "错误号: 412" in message:
            raise SystemExit(
                "B 站返回 412 风控拒绝。请使用 --login 扫码，或把浏览器里 "
                "bilibili.com 的整段 Cookie 保存到 "
                f"{COOKIE_FILE} 后重试。扫码成功后脚本会缓存凭据到 {CREDENTIAL_FILE}。"
            ) from exc
        raise
    finally:
        await get_client().close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="获取 Geekerwan 最新投稿视频的点赞量。"
    )
    parser.add_argument(
        "--object-file",
        type=Path,
        default=DEFAULT_OBJECT_FILE,
        help="包含 B 站空间 URL 的 JSON 文件。",
    )
    parser.add_argument("--uid", type=int, default=None, help="直接指定 UP 主 UID。")
    parser.add_argument(
        "--login",
        action="store_true",
        help="环境变量未提供 cookie 时，使用二维码登录。",
    )
    parser.add_argument(
        "--print-terminal-qrcode",
        action="store_true",
        help="同时在终端打印二维码色块；默认只保存 PNG 文件。",
    )
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(async_main(parse_args()))
