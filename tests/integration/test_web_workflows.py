"""Browser workflows exercised with simulated Bilibili responses."""

from contextlib import ExitStack
from datetime import datetime
import unittest
from unittest.mock import AsyncMock, Mock, patch

from bilibili_ds.web import actions, state, videos


class WebWorkflowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.items = [
            {"bvid": f"BV{day}", "title": f"Video {day}",
             "pubdate": int(datetime(2026, 9, day).timestamp()),
             "stat": {"view": day * 10, "like": day}}
            for day in (3, 2, 1)
        ]
        self.uploader = Mock()
        self.uploader.get_videos = AsyncMock(return_value={"page": {"count": 3}, "list": {"vlist": self.items}})
        self.stack.enter_context(patch.object(videos.user, "User", return_value=self.uploader))
        self.stack.enter_context(patch.object(videos, "selected_up", return_value={"uid": "42", "name": "Example"}))
        self.stack.enter_context(patch.object(videos.account_service, "credential_from_env", return_value=None))
        self.stack.enter_context(patch.object(videos.client, "configure_bilibili_client"))
        self.close = self.stack.enter_context(patch.object(videos.client, "close_bilibili_client", new_callable=AsyncMock))
        self.stack.enter_context(patch.object(videos.asyncio, "sleep", new_callable=AsyncMock))
        self.stack.enter_context(patch.object(videos.video_service, "fetch_video_detail", new_callable=AsyncMock, side_effect=lambda item, credential: dict(item)))
        self.stack.enter_context(patch.object(state, "PROGRESS", {"running": False, "message": "Idle.", "percent": 0, "count": None}))

    async def test_all_selection_modes(self):
        cases = [
            ({"kind": "position", "start": 1, "end": 2}, ["BV2", "BV3"]),
            ({"kind": "published", "start_time": "2026-09-02", "end_time": "2026-09-03"}, ["BV2", "BV3"]),
            ({"kind": "metric", "metric": "views", "minimum": 10, "maximum": 30}, ["BV2"]),
        ]
        for selection, expected in cases:
            with self.subTest(selection=selection):
                items, _, total = await videos.fetch_selected_video_items({"action": "analysis", "selection": selection})
                self.assertEqual([item["bvid"] for item in items], expected)
                self.assertEqual(total, 3)
        self.assertEqual(self.close.await_count, 3)

    async def test_invalid_selection_still_closes_client(self):
        with self.assertRaisesRegex(ValueError, "Start time and end time"):
            await videos.fetch_selected_video_items({"selection": {"kind": "published"}})
        self.close.assert_awaited_once()

    async def test_analysis_division_and_plot_results(self):
        self.stack.enter_context(patch.object(actions, "fetch_selected_video_items", new_callable=AsyncMock, return_value=(self.items, "all", 3)))
        self.stack.enter_context(patch.object(actions, "selected_up", return_value={"uid": "42", "name": "Example"}))
        save = self.stack.enter_context(patch.object(actions, "save_web_plot_png", return_value="sample.png"))
        listing = await actions.execute_video_action({"action": "list"})
        self.assertEqual(listing["count"], 3)
        analysis = await actions.execute_video_action({"action": "analysis"})
        self.assertEqual(analysis["summaries"][0]["mean"], 20)
        division = await actions.execute_video_action({"action": "division", "mode": "aggregate"})
        self.assertEqual(division["ratio"], 0.1)
        division = await actions.execute_video_action({"action": "division", "mode": "single"})
        self.assertEqual([row["ratio"] for row in division["rows"]], [0.1] * 3)
        plot = await actions.execute_video_action({"action": "plot", "field": "views"})
        self.assertEqual([point["value"] for point in plot["points"]], [30, 20, 10])
        self.assertEqual(plot["plot_file"], "sample.png")
        save.assert_called_once()
        self.assertFalse(state.PROGRESS["running"])
        self.assertEqual(state.PROGRESS["percent"], 100)

    async def test_single_video_lookup_reports_progress_and_closes_client(self):
        with patch.object(videos.video, "Video") as video:
            video.return_value.get_info = AsyncMock(return_value={"bvid": "BV1xx411c7mD", "stat": {"view": 0}})
            result = await videos.fetch_single_video("BV1xx411c7mD")
        self.assertEqual(result["views"], 0)
        self.assertFalse(state.PROGRESS["running"])
        self.assertEqual(state.PROGRESS["count"], 1)
        self.close.assert_awaited_once()
