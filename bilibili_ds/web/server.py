"""HTTP server lifecycle and optional browser launch."""

from __future__ import annotations

from argparse import Namespace
from http.server import ThreadingHTTPServer
import subprocess
import webbrowser

from bilibili_ds.web.routes import BilibiliDataScienceHandler


def create_server(host: str, start_port: int, retries: int) -> tuple[ThreadingHTTPServer, int]:
    last_error: OSError | None = None
    for port in range(start_port, start_port + max(retries, 0) + 1):
        try:
            return ThreadingHTTPServer((host, port), BilibiliDataScienceHandler), port
        except OSError as exc:
            last_error = exc
            if exc.errno not in (48, 98, 10048):
                raise
            print(f"Port {port} is already in use.")
            continue
    raise OSError(f"Could not bind {host}:{start_port}-{start_port + retries}") from last_error


def open_browser(url: str, browser_name: str) -> None:
    if browser_name == "none":
        return
    if browser_name == "chrome":
        try:
            subprocess.run(["open", "-a", "Google Chrome", url], check=False)
            return
        except OSError as exc:
            print(f"Could not open Google Chrome directly: {exc}")
    webbrowser.open(url)


def main(args: Namespace) -> None:
    server, port = create_server(args.host, args.port, args.port_retries)
    url = f"http://{args.host}:{port}"
    print(f"Serving Bilibili Data Science web UI at {url}")
    if args.open_browser:
        open_browser(url, args.browser)
    print("Press Ctrl+C to stop the server.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping web server.")
    finally:
        server.server_close()
