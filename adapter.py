from __future__ import annotations
from typing import Iterable


class Adapter:
    """Base class for benchmark adapters.

    The benchmark harness will import this and instantiate a subclass to test
    against our engine. Three methods required.
    """

    def ingest(self, events: Iterable[dict]) -> None:
        raise NotImplementedError

    def reconstruct_context(self, signal: dict, mode: str = "fast") -> dict:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError
