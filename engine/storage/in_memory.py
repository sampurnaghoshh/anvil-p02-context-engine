from __future__ import annotations

import bisect
from collections import defaultdict
from typing import Iterable


class InMemoryBackend:
    """
    Default storage backend — wraps the original EventMemory data structures.
    Behaviour is byte-identical to the pre-abstraction implementation.
    """

    def __init__(self) -> None:
        self._events: list[dict] = []
        self._ts_keys: list[float] = []
        self._id_index: dict[str, dict] = {}
        self._alias_map: dict[str, str] = {}
        # Inverse of alias_map: canonical → set of all names that map to it.
        # Never exposed outside this class; used only by get_members / set_alias.
        self._canon_members: dict[str, set[str]] = defaultdict(set)
        self._root_map: dict[str, str] = {}

    # ── Events ────────────────────────────────────────────────────────────────

    def append_event(self, event: dict) -> None:
        ts = float(event.get("ts", 0.0))
        pos = bisect.bisect_right(self._ts_keys, ts)
        self._events.insert(pos, event)
        self._ts_keys.insert(pos, ts)
        eid = event.get("id")
        if eid:
            self._id_index[eid] = event

    def get_event(self, event_id: str) -> dict | None:
        return self._id_index.get(event_id)

    def events_in_window(self, end_ts: float, seconds_before: float) -> list[dict]:
        start_ts = end_ts - seconds_before
        lo = bisect.bisect_left(self._ts_keys, start_ts)
        hi = bisect.bisect_right(self._ts_keys, end_ts)
        return self._events[lo:hi]

    def all_events(self) -> Iterable[dict]:
        return iter(self._events)

    def count_events(self) -> int:
        return len(self._events)

    # ── Alias map ─────────────────────────────────────────────────────────────

    def set_alias(self, name: str, canonical: str) -> None:
        old_canon = self._alias_map.get(name)
        if old_canon is not None:
            self._canon_members[old_canon].discard(name)
            if not self._canon_members[old_canon]:
                del self._canon_members[old_canon]
        self._alias_map[name] = canonical
        self._canon_members[canonical].add(name)

    def get_alias(self, name: str) -> str | None:
        return self._alias_map.get(name)

    def remove_alias(self, name: str) -> None:
        canon = self._alias_map.pop(name, None)
        if canon is not None:
            self._canon_members[canon].discard(name)
            if not self._canon_members[canon]:
                del self._canon_members[canon]

    def get_members(self, canonical: str) -> set[str]:
        return set(self._canon_members.get(canonical, set()))

    def all_aliases(self) -> dict[str, str]:
        return dict(self._alias_map)

    # ── Root map ──────────────────────────────────────────────────────────────

    def set_root(self, canonical: str, root: str) -> None:
        self._root_map[canonical] = root

    def get_root(self, canonical: str) -> str | None:
        return self._root_map.get(canonical)

    def remove_root(self, canonical: str) -> None:
        self._root_map.pop(canonical, None)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def clear(self) -> None:
        self._events.clear()
        self._ts_keys.clear()
        self._id_index.clear()
        self._alias_map.clear()
        self._canon_members.clear()
        self._root_map.clear()
