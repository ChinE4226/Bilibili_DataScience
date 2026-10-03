"""One replaceable RAM-only working dataset. Nothing is serialized to disk."""

from copy import deepcopy
from datetime import datetime, timezone
import json
from threading import Lock

from bilibili_ds import accounts
from bilibili_ds.web.creators import selected_creator

LOCK = Lock()
CURRENT = None


def context_key(payload):
    selected = selected_creator()
    return (str((selected or {}).get("uid")), accounts.active_account_id(),
            json.dumps(payload.get("selection") or {}, sort_keys=True))


async def acquire(payload, fetch):
    global CURRENT
    key = context_key(payload)
    if not payload.get("refresh") and CURRENT is not None and CURRENT["key"] == key:
        return deepcopy(CURRENT["data"]), {**CURRENT["meta"], "reused": True}
    if payload.get("reuse_only") and not payload.get("refresh"):
        raise ValueError("Click Fetch / Refresh to load this Creator and selection into memory first.")
    started = datetime.now(timezone.utc).isoformat()
    items, label, total, collection = await fetch(payload)
    data = (items, label, total)
    if context_key(payload) != key:
        raise ValueError("Creator or account changed during collection. Fetch again.")
    meta = {"started_at": started, "collected_at": datetime.now(timezone.utc).isoformat(),
            "count": len(data[0]), "selection": data[1], "uid": key[0], "collection": collection}
    CURRENT = {"key": key, "data": deepcopy(data), "meta": meta}
    return data, {**meta, "reused": False}
