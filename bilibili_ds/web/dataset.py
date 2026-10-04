"""Creator dataset and bounded sampling collections retained only in RAM."""

from copy import deepcopy
from collections import OrderedDict
from datetime import datetime, timezone
import json
from threading import Lock
from uuid import uuid4

from bilibili_ds import accounts
from bilibili_ds.web.creators import selected_creator

LOCK = Lock()
CURRENT = None
COHORT_LIMIT = 4
COHORT_ROW_LIMIT = 2500
COHORTS = OrderedDict()
COHORT_LOCK = Lock()


def retain_collection(items, *, kind, label, started_at, collected_at, collection, scope):
    """Retain trusted collected rows, never accept uploaded metrics or write files."""
    if kind not in {'weekly', 'random'} or len(items) > COHORT_ROW_LIMIT:
        raise ValueError('This collection exceeds the in-memory analysis limit.')
    identity = uuid4().hex
    meta = {'collection_id': identity, 'source_kind': kind, 'source_label': label,
            'started_at': started_at, 'collected_at': collected_at, 'count': len(items),
            'selection': label, 'uid': None, 'collection': deepcopy(collection), 'scope': deepcopy(scope)}
    from bilibili_ds.web.serializers import sort_by_published_time
    with COHORT_LOCK:
        COHORTS[identity] = {'data': (deepcopy(sort_by_published_time(items)), label, len(items)), 'meta': meta}
        while len(COHORTS) > COHORT_LIMIT:
            COHORTS.popitem(last=False)
    return deepcopy(meta)


def collection_entries():
    with COHORT_LOCK:
        return [deepcopy(entry['meta']) for entry in reversed(list(COHORTS.values()))]


def creator_metadata():
    current = CURRENT
    if current and current.get('key', ())[:2] == context_key({})[:2]:
        return deepcopy(current['meta'])
    return None


def context_key(payload):
    selected = selected_creator()
    return (str((selected or {}).get("uid")), accounts.active_account_id(),
            json.dumps(payload.get("selection") or {}, sort_keys=True))


async def acquire(payload, fetch):
    global CURRENT
    identity = payload.get('collection_id')
    if identity is not None and identity != '':
        if payload.get('refresh'):
            raise ValueError('Recollect this source on Sampling; Analysis only reuses its collected rows.')
        with COHORT_LOCK:
            entry = COHORTS.get(identity) if isinstance(identity, str) else None
            if entry is None:
                raise ValueError('This collection has expired or the server restarted. Collect it again on Sampling.')
            return deepcopy(entry['data']), {**deepcopy(entry['meta']), 'reused': True}
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
            "count": len(data[0]), "selection": data[1], "uid": key[0], "collection": collection,
            "source_kind": "creator", "source_label": f"Creator {(selected_creator() or {}).get('name') or key[0]}"}
    CURRENT = {"key": key, "data": deepcopy(data), "meta": meta}
    return data, {**meta, "reused": False}
