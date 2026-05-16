from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class EventMapper(Protocol):
    """
    Protocol for translating raw harness events into engine-native dicts
    and translating engine output back to harness-expected field names.

    map_event  — ingest side: raw harness event → engine event (None = drop)
    map_signal — query side: raw harness signal → engine signal (never None)
    unmap_context — output side: engine Context dict → harness Context dict
    """

    def map_event(self, raw: dict) -> dict | None: ...
    def map_signal(self, raw: dict) -> dict: ...
    def unmap_context(self, ctx: dict) -> dict: ...


class IdentityMapper:
    """No-op mapper — passes everything through unchanged."""

    def map_event(self, raw: dict) -> dict | None:
        return raw

    def map_signal(self, raw: dict) -> dict:
        return raw

    def unmap_context(self, ctx: dict) -> dict:
        return ctx
