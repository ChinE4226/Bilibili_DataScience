"""Offline integration checks for the extracted application modules."""

from contextlib import ExitStack, redirect_stdout
from datetime import datetime
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

from bilibili_api import Credential, user

from bilibili_ds import accounts, client, config, plotting, state, storage, videos
from bilibili_ds.cli import accounts as account_ui
from bilibili_ds.cli import prompts


ROOT = Path(__file__).resolve().parents[2]


class IsolatedFilesTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        for name in ("UPS_FILE", "COOKIE_FILE", "QRCODE_FILE", "LEGACY_CREDENTIAL_FILE", "ACTIVE_ACCOUNT_FILE", "ACCOUNTS_DIR", "PLOTS_DIR"):
            self.stack.enter_context(patch.object(config, name, self.root / name.lower()))
        self.stack.enter_context(patch.dict(os.environ, {}, clear=True))
        self.stack.enter_context(patch.multiple(state, REQUEST_FREQUENCY=4.0, USE_GUEST_MODE=False, SELECTED_UID=None))

    def test_storage_migration_selection_and_paths(self):
        storage.write_json(config.UPS_FILE, {"selected_uid": "2", "ups": [{"uid": 1}, {"uid": 2}]})
        self.assertEqual(storage.load_selected_up()["uid"], "2")
        self.assertEqual(state.SELECTED_UID, "2")
        self.assertNotIn("selected_uid", storage.read_json(config.UPS_FILE))
        storage.save_selected_up({"uid": 3, "name": "Third"})
        self.assertEqual(storage.load_uid(config.UPS_FILE), 3)
        self.assertEqual(len(storage.load_ups()), 3)
        self.assertEqual(config.PROJECT_ROOT, ROOT)

    def test_account_save_load_precedence_and_cleanup(self):
        credential = Credential(sessdata="cached", bili_jct="test", dedeuserid="42")
        record = accounts.account_record_from_credential(credential, name="Cached")
        accounts.save_account_record(record)
        self.assertEqual(accounts.active_account_id(), "42")
        self.assertEqual(accounts.credential_from_cache().sessdata, "cached")
        self.assertEqual(len(accounts.load_account_records()), 1)
        with patch.dict(os.environ, {"BILI_COOKIE": "SESSDATA=environment; DedeUserID=99"}):
            self.assertEqual(accounts.credential_from_env().sessdata, "environment")
            self.assertEqual(accounts.active_account_record()["id"], "42")
        self.assertEqual(accounts.clear_all_account_caches(), 3)
        self.assertEqual(accounts.load_account_records(), [])

    def test_legacy_account_cache_is_still_readable(self):
        storage.write_json(config.LEGACY_CREDENTIAL_FILE, {"sessdata": "old", "dedeuserid": "24"})
        self.assertEqual(accounts.credential_from_cache().sessdata, "old")
        self.assertEqual(accounts.active_account_record()["source"], "legacy")

    def test_guest_mode_and_request_rate_are_shared(self):
        with patch.object(accounts, "credential_from_env") as credentials, redirect_stdout(io.StringIO()):
            account_ui.use_service_without_sign_in()
            self.assertIsNone(accounts.credential_for_requests())
            credentials.assert_not_called()
        with patch("builtins.input", side_effect=["2", "8"]), redirect_stdout(io.StringIO()):
            prompts.set_request_frequency()
        self.assertEqual(state.REQUEST_FREQUENCY, 8)
        self.assertEqual(client.request_delay_seconds(), 0.125)
        state.REQUEST_FREQUENCY = 2
        self.assertEqual(client.request_delay_seconds(), 0.5)

    def test_png_plot_uses_configured_output_directory(self):
        output = plotting.save_line_plot(
            selected_up={"name": "Example", "uid": "42"}, selection_label="All videos",
            plot_label="Likes", y_label="Likes",
            x_values=[datetime(2026, 1, 1), datetime(2026, 1, 2)], y_values=[10, 11],
        )
        self.assertEqual(output.parent, config.PLOTS_DIR)
        self.assertTrue(output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(plotting.plt.get_fignums(), [])

    def test_web_png_plot_with_dates_and_fallback_labels(self):
        from bilibili_ds.web.plots import save_web_plot_png

        for labels in (("2026-09-01 12:00:00", "2026-09-02 12:00:00"), ("First", "Second")):
            with self.subTest(labels=labels):
                name = save_web_plot_png(
                    {"name": "Example", "uid": "42"}, "All videos", "Views", "Views",
                    [{"title": "A", "label": labels[0], "value": 10}, {"title": "B", "label": labels[1], "value": 20}],
                )
                self.assertTrue((config.PLOTS_DIR / name).read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
                self.assertEqual(plotting.plt.get_fignums(), [])


class FetchTests(unittest.IsolatedAsyncioTestCase):
    async def test_video_detail_success_and_failure(self):
        with patch.object(videos.video, "Video") as video_type:
            video_type.return_value.get_info = AsyncMock(return_value={"title": "Full title", "stat": {"view": 5}})
            result = await videos.fetch_video_detail({"bvid": "BV-test", "created": 100}, None)
            self.assertEqual(result["stat"], {"view": 5})
            self.assertEqual(result["pubdate"], 100)
            video_type.return_value.get_info.side_effect = RuntimeError("offline")
            result = await videos.fetch_video_detail({"bvid": "BV-test"}, None)
            self.assertEqual(result["detail_error"], "offline")
            video_type.reset_mock()
            self.assertEqual((await videos.fetch_video_detail({}, None))["detail_error"], "No BVID available.")
            video_type.assert_not_called()

    async def test_pagination_truncates_and_uses_shared_rate(self):
        uploader = Mock()
        uploader.get_videos = AsyncMock(side_effect=[
            {"list": {"vlist": [{"bvid": "A"}, {"bvid": "B"}]}},
            {"list": {"vlist": [{"bvid": "C"}, {"bvid": "D"}]}},
        ])
        with patch.object(state, "REQUEST_FREQUENCY", 8), patch.object(videos.asyncio, "sleep", new_callable=AsyncMock) as sleep:
            result = await videos.fetch_video_summaries(uploader, 3, user.VideoOrder.PUBDATE)
        self.assertEqual([item["bvid"] for item in result], ["A", "B", "C"])
        self.assertEqual(uploader.get_videos.await_args_list[1].kwargs["pn"], 2)
        self.assertEqual(sleep.await_count, 2)
        sleep.assert_awaited_with(0.125)

    async def test_client_cleanup_after_account_error(self):
        credential = Mock()
        credential.has_sessdata.return_value = True
        credential.check_valid = AsyncMock(side_effect=RuntimeError("offline"))
        with patch.object(accounts, "configure_bilibili_client"), patch.object(accounts, "close_bilibili_client", new_callable=AsyncMock) as close:
            self.assertEqual(await accounts.load_account_detail(credential), (None, None, "offline"))
        close.assert_awaited_once()


class EntryPointTests(unittest.TestCase):
    def test_direct_script_from_another_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / "bilibili_ds", root / "bilibili_ds", ignore=shutil.ignore_patterns("__pycache__"))
            (root / "main").mkdir()
            shutil.copy2(ROOT / "main/main.py", root / "main/main.py")
            env = {key: value for key, value in os.environ.items() if not key.startswith("BILI_")}
            env.update(MPLCONFIGDIR=str(root / "matplotlib"), XDG_CACHE_HOME=str(root / "cache"))
            result = subprocess.run(
                [sys.executable, str(root / "main/main.py")], cwd=root.parent, env=env,
                input="1\n3\n4\n2\n8\n5\n3\nExample\nhttps://space.bilibili.com/42\n0\n",
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Account: Guest mode", result.stdout)
            self.assertIn("Request frequency: 8 request(s) per second", result.stdout)
            self.assertIn("Selected UP: Example (UID 42)", result.stdout)
            self.assertEqual(storage.read_json(root / "objects/ups.json")["ups"][0]["uid"], "42")
            result = subprocess.run(
                [sys.executable, "-m", "bilibili_ds"], cwd=root, env=env,
                input="0\n", capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Selected UP: Example (UID 42)", result.stdout)

    def test_both_web_launchers_offer_the_same_options(self):
        outputs = []
        for command in ([sys.executable, "web_server.py", "--help"],
                        [sys.executable, "-m", "bilibili_ds.web", "--help"]):
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("--no-reload", result.stdout)
            outputs.append(result.stdout.split("options:", 1)[-1])
        self.assertEqual(outputs[0], outputs[1])

    def test_web_imports_shared_modules_without_terminal_dependency(self):
        result = subprocess.run(
            [sys.executable, "-c", "import bilibili_ds.web.server; import sys; "
             "assert not any(n == 'bilibili_ds.cli' or n.startswith('bilibili_ds.cli.') for n in sys.modules); "
             "assert 'main.main' not in sys.modules"],
            cwd=ROOT, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
