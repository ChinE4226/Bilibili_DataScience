"""Bilibili network configuration, pacing, and cleanup."""

import asyncio

from bilibili_api import request_settings
from bilibili_api.utils import network

from bilibili_ds import state
from bilibili_ds.fetch_context import REQUEST_DELAY, check_canceled


def request_delay_seconds() -> float:
    check_canceled()
    if REQUEST_DELAY.get() is not None:
        return REQUEST_DELAY.get()
    return 1.0 / state.REQUEST_FREQUENCY


async def close_bilibili_client() -> None:
    """Release clients and SDK cache entries owned by this operation's loop."""
    loop = asyncio.get_running_loop()
    # The SDK's close() closes the transport but retains the loop in both caches.
    # Evict before awaiting close, including on cancellation; leave other loops alone.
    clients = [pool.pop(loop) for pool in list(network.session_pool.values()) if loop in pool]
    for pool in list(network.lazy_settings.values()):
        pool.pop(loop, None)
    for session in clients:
        try:
            await session.close()
        except Exception:
            pass


def configure_bilibili_client() -> None:
    request_settings.set_timeout(20)
    request_settings.set("impersonate", "chrome120")
    request_settings.set("http2", False)
