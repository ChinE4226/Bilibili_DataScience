"""Bilibili network configuration, pacing, and cleanup."""

from bilibili_api import get_client, request_settings

from bilibili_ds import state
from bilibili_ds.fetch_context import REQUEST_DELAY, check_canceled


def request_delay_seconds() -> float:
    check_canceled()
    if REQUEST_DELAY.get() is not None:
        return REQUEST_DELAY.get()
    return 1.0 / state.REQUEST_FREQUENCY


async def close_bilibili_client() -> None:
    try:
        await get_client().close()
    except Exception:
        pass


def configure_bilibili_client() -> None:
    request_settings.set_timeout(20)
    request_settings.set("impersonate", "chrome120")
    request_settings.set("http2", False)
