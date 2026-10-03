"""RAM reuse, refresh, isolation and local processing without network calls."""
from contextlib import ExitStack
import unittest
from unittest.mock import AsyncMock, patch
from bilibili_ds.web import actions, dataset


class DatasetTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(dataset, 'CURRENT', None))
        self.creator = self.stack.enter_context(patch.object(dataset, 'selected_creator', return_value={'uid': '42'}))
        self.account = self.stack.enter_context(patch.object(dataset.accounts, 'active_account_id', return_value=None))
        self.items = [{'bvid': 'A', 'stat': {'view': 100, 'like': 10}}, {'bvid': 'B', 'stat': {'view': 500}}, {'bvid': 'C', 'stat': {'like': 30}}]
        self.fetch = self.stack.enter_context(patch.object(actions, 'fetch_selected_video_items', new_callable=AsyncMock, return_value=(self.items, 'sample', 3, {})))

    async def test_refresh_reuse_and_local_filter(self):
        first = await actions.execute_video_action({'action': 'list', 'refresh': True})
        second = await actions.execute_video_action({'action': 'analysis', 'reuse_only': True})
        self.assertTrue(second['dataset']['reused'])
        self.assertEqual(first['dataset']['collected_at'], second['dataset']['collected_at'])
        filtered = await actions.execute_video_action({'action': 'analysis', 'reuse_only': True, 'local_filter': {'minimum_views': 200}})
        self.assertEqual(filtered['count'], 1)
        self.fetch.assert_awaited_once()
        await actions.execute_video_action({'action': 'list', 'refresh': True})
        self.assertEqual(self.fetch.await_count, 2)

    async def test_context_changes_require_explicit_fetch(self):
        await actions.execute_video_action({'action': 'list', 'refresh': True})
        for change in [{'selection': {'kind': 'position'}}, {}]:
            if not change:
                self.account.return_value = 'other'
            with self.assertRaisesRegex(ValueError, 'Fetch / Refresh'):
                await actions.execute_video_action({'action': 'analysis', 'reuse_only': True, **change})
        self.account.return_value = None
        self.creator.return_value = {'uid': '99'}
        with self.assertRaisesRegex(ValueError, 'Fetch / Refresh'):
            await actions.execute_video_action({'action': 'analysis', 'reuse_only': True})
        self.fetch.assert_awaited_once()

    async def test_failed_refresh_preserves_previous_dataset(self):
        await actions.execute_video_action({'action': 'list', 'refresh': True})
        self.fetch.side_effect = ValueError('offline')
        with self.assertRaisesRegex(ValueError, 'offline'):
            await actions.execute_video_action({'action': 'list', 'refresh': True})
        result = await actions.execute_video_action({'action': 'analysis', 'reuse_only': True})
        self.assertEqual(result['count'], 3)

    async def test_aggregate_uses_matched_rows(self):
        result = await actions.execute_video_action({'action': 'division', 'mode': 'aggregate', 'refresh': True})
        self.assertEqual(result['ratio'], .1)
        self.assertEqual(result['eligible_count'], 1)
        self.assertEqual(result['excluded_count'], 2)

    async def test_overlapping_operation_is_rejected(self):
        with dataset.LOCK:
            with self.assertRaisesRegex(ValueError, 'Another video operation'):
                await actions.execute_video_action({'action': 'list'})
        self.fetch.assert_not_awaited()

    async def test_collection_counts_survive_reuse_and_view_filter(self):
        collection = {'requested': 3, 'examined': 5, 'skipped_invalid': 2, 'shortfall': 0}
        self.fetch.return_value = (self.items, 'sample', 5, collection)
        await actions.execute_video_action({'action': 'list', 'refresh': True})
        result = await actions.execute_video_action({'action': 'analysis', 'reuse_only': True,
            'local_filter': {'minimum_views': 200}})
        self.assertEqual(result['dataset']['collection'], collection)
        self.assertEqual(result['dataset']['count'], 3)
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['dataset']['filter_counts']['excluded'], 2)
        self.fetch.assert_awaited_once()
