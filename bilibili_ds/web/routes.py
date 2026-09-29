"""HTTP routes for the local dashboard and its assets."""

from __future__ import annotations

import asyncio
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
import mimetypes
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from bilibili_ds import config, state as settings
from bilibili_ds.web import state
from bilibili_ds.web.accounts import (
    account_detail,
    account_records_summary,
    account_summary,
    qr_sign_in_status,
    select_account,
    sign_out_web,
    start_qr_sign_in,
)
from bilibili_ds.web.actions import execute_video_action
from bilibili_ds.web.assets import STATIC_CONTENT_TYPES, dashboard_html, static_file
from bilibili_ds.web.creators import add_web_up, load_web_ups, select_up_by_uid, selected_up
from bilibili_ds.web.http import json_bytes, read_json_body
from bilibili_ds.web.plots import plot_entries
from bilibili_ds.web.videos import fetch_single_video, selected_up_detail


class BilibiliDataScienceHandler(BaseHTTPRequestHandler):
    server_version = "BilibiliDataScienceWeb/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}")

    def send_bytes(
        self,
        body: bytes,
        content_type: str,
        status: HTTPStatus = HTTPStatus.OK,
        *,
        send_body: bool = True,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if send_body:
            self.wfile.write(body)

    def send_json(self, data: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_bytes(json_bytes(data), "application/json; charset=utf-8", status)

    def send_error_json(self, status: HTTPStatus, message: str) -> None:
        self.send_json({"error": message}, status)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            self.send_bytes(dashboard_html(), "text/html; charset=utf-8")
            return
        if path.startswith("/static/"):
            self.serve_static(path.removeprefix("/static/"))
            return
        if path == "/api/dev-version":
            try:
                ups_revision = config.UPS_FILE.stat().st_mtime_ns
            except FileNotFoundError:
                ups_revision = 0
            self.send_json({"token": state.RELOAD_TOKEN, "ups_revision": str(ups_revision)})
            return
        if path == "/api/health":
            self.send_json(
                {
                    "ok": True,
                    "selected_up": selected_up(),
                    "account": account_summary(),
                    "request_frequency": settings.REQUEST_FREQUENCY,
                }
            )
            return
        if path == "/api/ups":
            self.send_json({"ups": load_web_ups(), "selected_up": selected_up()})
            return
        if path == "/api/plots":
            self.send_json({"plots": plot_entries()})
            return
        if path == "/api/progress":
            self.send_json(state.PROGRESS)
            return
        if path == "/api/accounts":
            self.send_json({"accounts": account_records_summary()})
            return
        if path == "/api/account-detail":
            try:
                self.send_json(asyncio.run(account_detail()))
            except Exception as exc:
                self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            return
        if path == "/api/up-detail":
            try:
                self.send_json(asyncio.run(selected_up_detail()))
            except Exception as exc:
                self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            return
        if path == "/favicon.ico":
            self.send_bytes(b"", "image/x-icon", HTTPStatus.NO_CONTENT)
            return
        if path == "/runtime/qrcode.png":
            self.serve_qrcode()
            return
        if path.startswith("/plots/"):
            self.serve_plot(path.removeprefix("/plots/"))
            return

        self.send_error_json(HTTPStatus.NOT_FOUND, "Not found.")

    def do_HEAD(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            self.send_bytes(dashboard_html(), "text/html; charset=utf-8", send_body=False)
            return
        if path.startswith("/static/"):
            self.serve_static(path.removeprefix("/static/"), send_body=False)
            return
        if path == "/api/health":
            self.send_bytes(b"{}", "application/json; charset=utf-8", send_body=False)
            return
        if path == "/api/ups":
            self.send_bytes(b"{}", "application/json; charset=utf-8", send_body=False)
            return
        if path == "/api/plots":
            self.send_bytes(b"{}", "application/json; charset=utf-8", send_body=False)
            return
        if path == "/api/progress":
            self.send_bytes(b"{}", "application/json; charset=utf-8", send_body=False)
            return
        if path == "/api/accounts":
            self.send_bytes(b"{}", "application/json; charset=utf-8", send_body=False)
            return
        if path in {"/api/account-detail", "/api/up-detail"}:
            self.send_bytes(b"{}", "application/json; charset=utf-8", send_body=False)
            return
        if path == "/favicon.ico":
            self.send_bytes(b"", "image/x-icon", HTTPStatus.NO_CONTENT, send_body=False)
            return
        if path == "/runtime/qrcode.png":
            self.send_bytes(b"", "image/png", send_body=False)
            return
        if path.startswith("/plots/"):
            name = Path(unquote(path.removeprefix("/plots/"))).name
            plot_path = config.PLOTS_DIR / name
            if plot_path.is_file() and plot_path.suffix.lower() == ".png":
                content_type = mimetypes.guess_type(plot_path.name)[0] or "application/octet-stream"
                self.send_bytes(b"", content_type, send_body=False)
                return

        self.send_bytes(b"", "application/json; charset=utf-8", HTTPStatus.NOT_FOUND, send_body=False)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path not in {
            "/api/selected-up",
            "/api/ups/add",
            "/api/video-lookup",
            "/api/video-action",
            "/api/request-frequency",
            "/api/sign-out",
            "/api/account/select",
            "/api/sign-in/qr/start",
            "/api/sign-in/qr/status",
        }:
            self.send_error_json(HTTPStatus.NOT_FOUND, "Not found.")
            return

        try:
            data = read_json_body(self)
        except ValueError as exc:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            return

        try:
            if path == "/api/selected-up":
                uid = str(data.get("uid") or "").strip()
                if not uid:
                    raise ValueError("uid is required.")
                entry = select_up_by_uid(uid)
                if entry is None:
                    self.send_error_json(HTTPStatus.NOT_FOUND, "UP was not found.")
                    return
                self.send_json({"selected_up": entry})
                return
            if path == "/api/ups/add":
                entry = add_web_up(str(data.get("name") or "").strip(), str(data.get("space") or "").strip())
                self.send_json({"up": entry})
                return
            if path == "/api/video-lookup":
                self.send_json({"video": asyncio.run(fetch_single_video(data.get("video")))})
                return
            if path == "/api/video-action":
                self.send_json(asyncio.run(execute_video_action(data)))
                return
            if path == "/api/request-frequency":
                value = float(data.get("value"))
                if value <= 0:
                    raise ValueError("Request frequency must be greater than 0.")
                settings.REQUEST_FREQUENCY = value
                self.send_json({"request_frequency": settings.REQUEST_FREQUENCY})
                return
            if path == "/api/sign-out":
                self.send_json(sign_out_web(str(data.get("mode") or "keep")))
                return
            if path == "/api/account/select":
                self.send_json({"account": select_account(str(data.get("id") or ""))})
                return
            if path == "/api/sign-in/qr/start":
                self.send_json(asyncio.run(start_qr_sign_in()))
                return
            if path == "/api/sign-in/qr/status":
                self.send_json(asyncio.run(qr_sign_in_status()))
                return
        except Exception as exc:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))

    def serve_static(self, raw_name: str, *, send_body: bool = True) -> None:
        path = static_file(raw_name)
        try:
            if path is not None:
                body = path.read_bytes()
                self.send_bytes(body, STATIC_CONTENT_TYPES[path.suffix], send_body=send_body)
                return
        except OSError:
            pass
        self.send_bytes(b"", "text/plain; charset=utf-8", HTTPStatus.NOT_FOUND, send_body=send_body)

    def serve_plot(self, raw_name: str) -> None:
        name = Path(unquote(raw_name)).name
        path = config.PLOTS_DIR / name
        try:
            resolved = path.resolve()
            plots_root = config.PLOTS_DIR.resolve()
        except OSError:
            self.send_error_json(HTTPStatus.NOT_FOUND, "Plot was not found.")
            return

        if plots_root not in resolved.parents or not resolved.is_file() or resolved.suffix.lower() != ".png":
            self.send_error_json(HTTPStatus.NOT_FOUND, "Plot was not found.")
            return

        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_bytes(resolved.read_bytes(), content_type)

    def serve_qrcode(self) -> None:
        path = config.QRCODE_FILE
        if not path.is_file():
            self.send_error_json(HTTPStatus.NOT_FOUND, "QR code is not available.")
            return
        self.send_bytes(path.read_bytes(), "image/png")
