"""SDK session lifetimes across repeated checks, without network requests."""

import asyncio
import gc
import unittest
import weakref
from unittest.mock import patch

from bilibili_api.utils import network
from bilibili_ds import client


class OfflineClient:
    def __init__(self):
        self.closed = False

    async def close(self):
        self.closed = True


class ClientCleanupTests(unittest.TestCase):
    def setUp(self):
        self.pools, self.settings = {'offline': {}}, {'offline': {}}
        mocks = patch.multiple(network, selected_client='offline',
            sessions={'offline': OfflineClient}, client_settings={'offline': []},
            session_pool=self.pools, lazy_settings=self.settings)
        mocks.start()
        self.addCleanup(mocks.stop)

    def test_repeated_operations_release_clients_and_event_loops(self):
        references = []

        async def check():
            session = network.get_client()  # Exercise the installed SDK's actual cache.
            references.append((weakref.ref(asyncio.get_running_loop()), weakref.ref(session)))
            await client.close_bilibili_client()
            self.assertTrue(session.closed)

        for _ in range(500):
            asyncio.run(check())
        gc.collect()
        self.assertEqual(self.pools['offline'], {})
        self.assertEqual(self.settings['offline'], {})
        self.assertTrue(all(loop() is None and session() is None for loop, session in references))

    def test_cleanup_does_not_create_an_unused_client(self):
        asyncio.run(client.close_bilibili_client())
        self.assertEqual(self.pools['offline'], {})
        self.assertEqual(self.settings['offline'], {})

    def test_other_loops_are_preserved_and_same_loop_can_fetch_again(self):
        other_loop = asyncio.new_event_loop()
        self.addCleanup(other_loop.close)
        other = OfflineClient()
        self.pools['offline'][other_loop] = other
        self.settings['offline'][other_loop] = {'timeout': 20}

        async def check():
            first = network.get_client()
            await client.close_bilibili_client()
            second = network.get_client()
            self.assertIsNot(first, second)
            self.assertFalse(second.closed)
            await client.close_bilibili_client()

        asyncio.run(check())
        self.assertFalse(other.closed)
        self.assertEqual(self.pools['offline'], {other_loop: other})
        self.assertEqual(self.settings['offline'], {other_loop: {'timeout': 20}})

    def test_failed_or_cancelled_close_still_evicts_the_loop(self):
        for exception in (RuntimeError('transport failure'), asyncio.CancelledError()):
            async def check():
                session = network.get_client()
                async def fail():
                    raise exception
                session.close = fail
                await client.close_bilibili_client()

            if isinstance(exception, asyncio.CancelledError):
                with self.assertRaises(asyncio.CancelledError):
                    asyncio.run(check())
            else:
                asyncio.run(check())
            self.assertEqual(self.pools['offline'], {})
            self.assertEqual(self.settings['offline'], {})
