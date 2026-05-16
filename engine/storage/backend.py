from __future__ import annotations

from typing import Iterable, Protocol, runtime_checkable


@runtime_checkable
class StorageBackend(Protocol):
    """
    Protocol for EventMemory storage backends.

    Implementations must be swap-compatible: InMemoryBackend for default use,
    SQLiteBackend for persistence. EventMemory delegates ALL state here.
    """

    # ── Events ────────────────────────────────────────────────────────────────

    def append_event(self, event: dict) -> None:
        """Insert event into the store, maintaining ts-ordered retrieval."""
        ...

    def get_event(self, event_id: str) -> dict | None:
        """Return the event with the given id, or None."""
        ...

    def events_in_window(self, end_ts: float, seconds_before: float) -> list[dict]:
        """Return events whose ts falls in [end_ts - seconds_before, end_ts], ts-ordered."""
        ...

    def all_events(self) -> Iterable[dict]:
        """Lazy iteration over all events in ts order. Memory-bounded for large stores."""
        ...

    def count_events(self) -> int:
        """Return the total number of stored events without materialising them."""
        ...

    # ── Alias map ─────────────────────────────────────────────────────────────

    def set_alias(self, name: str, canonical: str) -> None:
        """Record that `name` is an alias for `canonical`."""
        ...

    def get_alias(self, name: str) -> str | None:
        """Return the canonical that `name` maps to, or None if not aliased."""
        ...

    def remove_alias(self, name: str) -> None:
        """Delete the alias entry for `name` (no-op if absent)."""
        ...

    def get_members(self, canonical: str) -> set[str]:
        """Return the set of all names whose current canonical is `canonical`."""
        ...

    def all_aliases(self) -> dict[str, str]:
        """Return a snapshot of the full alias map {name: canonical}."""
        ...

    # ── Root map ──────────────────────────────────────────────────────────────

    def set_root(self, canonical: str, root: str) -> None:
        """Record the rename-invariant first-seen name for `canonical`."""
        ...

    def get_root(self, canonical: str) -> str | None:
        """Return the root for `canonical`, or None if not recorded."""
        ...

    def remove_root(self, canonical: str) -> None:
        """Delete the root entry for `canonical` (no-op if absent)."""
        ...

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def clear(self) -> None:
        """Reset all stored state — used by demo reset and tests."""
        ...
