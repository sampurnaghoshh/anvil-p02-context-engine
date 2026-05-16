from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from engine.storage.in_memory import InMemoryBackend

if TYPE_CHECKING:
    from engine.storage.backend import StorageBackend


class EventMemory:
    """
    Append-only event store with rename-invariant alias resolution.

    All state is delegated to a StorageBackend. Defaults to InMemoryBackend,
    which preserves the original bisect-based O(log n) behaviour exactly.
    Pass backend=SQLiteBackend(path) for persistent storage.
    """

    def __init__(self, backend: "StorageBackend | None" = None) -> None:
        self.backend: StorageBackend = backend if backend is not None else InMemoryBackend()

    # ── Ingestion ─────────────────────────────────────────────────────────────

    def ingest_one(self, event: dict) -> None:
        # Rename must be registered before the event is stored so that any
        # subsequent resolve() calls see the updated alias map immediately.
        if event.get("kind") == "topology" and event.get("change") == "rename":
            old = event.get("old_name") or event.get("from")
            new = event.get("new_name") or event.get("to")
            if old and new:
                self._apply_rename(old, new)
        self.backend.append_event(event)

    # ── Alias management ──────────────────────────────────────────────────────

    def _apply_rename(self, old_name: str, new_name: str) -> None:
        # Find the current canonical for old_name (may already be an alias)
        alias = self.backend.get_alias(old_name)
        canonical_old = alias if alias is not None else old_name

        # Collect all names that currently resolve to canonical_old, plus itself
        members = self.backend.get_members(canonical_old)
        members.add(canonical_old)

        # Point every member directly at new_name (single-hop, no chains)
        for name in members:
            self.backend.set_alias(name, new_name)

        # Carry the rename-invariant root forward to new_name
        existing_root = self.backend.get_root(canonical_old)
        root = existing_root if existing_root is not None else canonical_old
        self.backend.set_root(new_name, root)
        self.backend.remove_root(canonical_old)

    def resolve(self, name: str) -> str:
        """Return the current canonical name for any historical service name."""
        result = self.backend.get_alias(name)
        return result if result is not None else name

    def canonical_root(self, name: str) -> str:
        """Return the original first-seen name of this service identity.

        Rename-invariant: all aliases of the same service resolve to the same
        root regardless of how many renames have occurred.
        """
        if not name:
            return ""
        current = self.resolve(name)
        result = self.backend.get_root(current)
        return result if result is not None else current

    # ── Temporal queries ──────────────────────────────────────────────────────

    def events_in_window(self, end_ts: float, seconds_before: float) -> list[dict]:
        """Return all events whose ts falls in [end_ts - seconds_before, end_ts]."""
        return self.backend.events_in_window(end_ts, seconds_before)

    def get_by_id(self, event_id: str) -> Optional[dict]:
        return self.backend.get_event(event_id)

    # ── Public surface used by api/server.py ──────────────────────────────────

    def all_aliases(self) -> dict[str, str]:
        """Return a snapshot of the full alias map {name: canonical}."""
        return self.backend.all_aliases()

    # ── Dunder ────────────────────────────────────────────────────────────────

    def __len__(self) -> int:
        return self.backend.count_events()
