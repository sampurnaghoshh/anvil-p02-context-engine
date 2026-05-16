from __future__ import annotations
import sys
import os

# Make engine importable when adapter is loaded from any working directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Iterable
from adapter import Adapter
from engine.core import ContextEngine


class Engine(Adapter):
    """Anvil P-02 submission adapter — wraps ContextEngine for the benchmark."""

    def __init__(self) -> None:
        self._engine = ContextEngine()

    def ingest(self, events: Iterable[dict]) -> None:
        self._engine.ingest(events)

    def reconstruct_context(self, signal: dict, mode: str = "fast") -> dict:
        return self._engine.reconstruct_context(signal, mode=mode)

    def close(self) -> None:
        self._engine.close()
