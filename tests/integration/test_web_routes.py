"""Local HTTP checks for routes, public assets, and shared settings."""

from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import AsyncMock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from bilibili_ds import config, state as settings
from bilibili_ds.web import assets, plots, routes, state
from bilibili_ds.web.server import DashboardHTTPServer


class QuietHandler(routes.BilibiliDataScienceHandler):
    def log_message(self, *args):
        pass


class WebRouteTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        for name in ("CREATORS_FILE", "COOKIE_FILE", "QRCODE_FILE", "LEGACY_CREDENTIAL_FILE", "ACTIVE_ACCOUNT_FILE", "ACCOUNTS_DIR", "PLOTS_DIR"):
            self.stack.enter_context(patch.object(config, name, root / name.lower()))
        self.stack.enter_context(patch.object(settings, "REQUEST_FREQUENCY", 4.0))
        self.stack.enter_context(patch.object(state, "SELECTED_UID", None))
        self.stack.enter_context(patch.object(state, "RELOAD_TOKEN", "test-token"))
        self.stack.enter_context(patch.object(routes, "account_records_summary", return_value=[]))
        self.server = DashboardHTTPServer(("127.0.0.1", 0), QuietHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.stack.callback(self.stop_server)
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def request(self, path, data=None, method=None):
        body = None if data is None else json.dumps(data).encode()
        request = Request(self.base + path, data=body, method=method)
        if body is not None:
            request.add_header("Content-Type", "application/json")
        try:
            response = urlopen(request, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status, response.headers, response.read()

    def test_dashboard_and_every_browser_module_are_served(self):
        status, _, body = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn(b'type="module" src="/static/js/app.js"', body)
        self.assertIn(b'content="test-token"', body)
        self.assertNotIn(b"<style>", body)
        for path in config.STATIC_DIR.rglob("*"):
            if not path.is_file():
                continue
            with self.subTest(path=path):
                url = "/static/" + path.relative_to(config.STATIC_DIR).as_posix()
                status, headers, body = self.request(url)
                self.assertEqual(status, 200)
                self.assertEqual(body, path.read_bytes())
                self.assertEqual(headers["Content-Type"], assets.STATIC_CONTENT_TYPES[path.suffix])
                status, head_headers, head_body = self.request(url, method="HEAD")
                self.assertEqual(status, 200)
                self.assertEqual(head_headers["Content-Length"], str(len(body)))
                self.assertEqual(head_body, b"")

    def test_static_and_private_path_rejections(self):
        for path in ("/static/../README.md", "/static/%2e%2e/bilibili_ds/config.py", "/static/%2fetc/passwd",
                     "/static/missing.js", "/static/", "/.runtime/bilibili_credential.json", "/bilibili_ds/config.py"):
            with self.subTest(path=path):
                self.assertEqual(self.request(path)[0], 404)
                self.assertEqual(self.request(path, method="HEAD")[0], 404)

    def test_shared_request_rate_and_saved_creators(self):
        status, _, body = self.request("/api/request-frequency", {"value": 8})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"request_frequency": 8})
        self.assertEqual(settings.REQUEST_FREQUENCY, 8)
        self.assertEqual(json.loads(self.request("/api/health")[2])["request_frequency"], 8)
        self.assertEqual(self.request("/api/request-frequency", {"value": 0})[0], 400)
        status, _, body = self.request("/api/creators/add", {"name": "Example", "space": "https://space.bilibili.com/42"})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["creator"]["uid"], "42")
        self.assertEqual(json.loads(self.request("/api/creators")[2])["selected_creator"]["uid"], "42")
        self.assertNotIn("selected_uid", json.loads(config.CREATORS_FILE.read_text()))

    def test_lookup_and_actions_use_expected_route_contracts(self):
        with patch.object(routes, "fetch_single_video", new_callable=AsyncMock, return_value={"bvid": "BV1xx411c7mD"}) as lookup:
            status, _, body = self.request("/api/video-lookup", {"video": "BV1xx411c7mD"})
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body), {"video": {"bvid": "BV1xx411c7mD"}})
            lookup.assert_awaited_once_with("BV1xx411c7mD")
        with patch.object(routes, "execute_video_action", new_callable=AsyncMock, return_value={"count": 0}) as action:
            payload = {"action": "analysis", "selection": {"kind": "position", "start": 1, "end": 5}}
            self.assertEqual(self.request("/api/video-action", payload)[0], 200)
            action.assert_awaited_once_with(payload)
        self.assertEqual(self.request("/api/unknown", {})[0], 404)
        self.assertEqual(self.request("/api/selected-creator", {})[0], 400)

    def test_random_sample_route_returns_collection_and_handles_errors(self):
        with patch.object(routes, 'fetch_random_sample', new_callable=AsyncMock, return_value={'sampling': {'sampled': 100}}) as sampling:
            payload = {'keyword': 'camera', 'sample_size': 100}
            status, _, body = self.request('/api/random-sample', payload)
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)['sampling']['sampled'], 100)
            sampling.assert_awaited_once_with(payload)
            sampling.side_effect = ValueError('Invalid sample')
            self.assertEqual(self.request('/api/random-sample', {})[0], 400)

    def test_weekly_analysis_route_returns_collection_and_handles_errors(self):
        with patch.object(routes, 'fetch_weekly_analysis', new_callable=AsyncMock, return_value={'counts': {'included': 50}}) as weekly:
            status, _, body = self.request('/api/weekly-analysis', {'source': '393'})
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)['counts']['included'], 50)
            weekly.assert_awaited_once_with({'source': '393'})
            weekly.side_effect = ValueError('Invalid issue')
            self.assertEqual(self.request('/api/weekly-analysis', {'source': 'bad'})[0], 400)

    def test_plots_only_persist_after_explicit_save(self):
        points = [{"title": "Example", "label": "2026-09-01 12:00:00", "value": 12345}]
        plot_id = plots.prepare_plot({"name": "Example", "uid": "42"}, "all", "Views", "Views", points)
        self.assertFalse(config.PLOTS_DIR.exists())
        self.assertEqual(json.loads(self.request("/api/plots")[2]), {"plots": []})
        status, _, body = self.request("/api/plots/save", {"plot_id": plot_id})
        self.assertEqual(status, 200)
        saved = json.loads(body)
        self.assertEqual(len(list(config.PLOTS_DIR.glob("*.png"))), 1)
        self.assertTrue(self.request(saved["url"])[2].startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(json.loads(self.request("/api/plots/save", {"plot_id": plot_id})[2]), saved)
        self.assertEqual(len(list(config.PLOTS_DIR.glob("*.png"))), 1)
        number_payload = {"plot_id": plot_id, "axis_mode": "number"}
        number_save = json.loads(self.request("/api/plots/save", number_payload)[2])
        self.assertNotEqual(number_save["name"], saved["name"])
        self.assertEqual(json.loads(self.request("/api/plots/save", number_payload)[2]), number_save)
        self.assertEqual(len(list(config.PLOTS_DIR.glob("*.png"))), 2)
        self.assertEqual(self.request("/api/plots/save", {"plot_id": plot_id, "axis_mode": "invalid"})[0], 400)
        ma_payload = {"plot_id": plot_id, "axis_mode": "number", "ma_periods": [5, 10]}
        ma_save = json.loads(self.request("/api/plots/save", ma_payload)[2])
        self.assertNotEqual(ma_save["name"], number_save["name"])
        self.assertEqual(json.loads(self.request("/api/plots/save", {**ma_payload, "ma_periods": [10, 5, 5]})[2]), ma_save)
        self.assertEqual(len(list(config.PLOTS_DIR.glob("*.png"))), 3)
        for invalid_periods in ([0], [True], ["5"], [1000000], "5"):
            self.assertEqual(self.request("/api/plots/save", {**ma_payload, "ma_periods": invalid_periods})[0], 400)
        indicator_payload = {**ma_payload, "indicators": ["ema10", "median5", "relative20"]}
        indicator_save = json.loads(self.request("/api/plots/save", indicator_payload)[2])
        self.assertNotEqual(indicator_save["name"], ma_save["name"])
        self.assertEqual(json.loads(self.request("/api/plots/save", {**indicator_payload, "indicators": ["relative20", "median5", "ema10", "ema10"]})[2]), indicator_save)
        self.assertEqual(len(list(config.PLOTS_DIR.glob("*.png"))), 4)
        for invalid in ([True], ["ema100"], "ema10", [20]):
            self.assertEqual(self.request("/api/plots/save", {**indicator_payload, "indicators": invalid})[0], 400)
        for invalid in (None, "", "expired", "../../unexpected.png", {"points": points}):
            self.assertEqual(self.request("/api/plots/save", {"plot_id": invalid})[0], 400)
