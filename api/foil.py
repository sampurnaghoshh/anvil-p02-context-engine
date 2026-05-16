"""
api/foil.py — Deliberately-naive baseline engine for the comparison demo.

Stores incidents as raw text blobs, retrieves by Jaccard token overlap.
Used to show judges what fails when you DON'T normalise service names.

Why it fails on renames
-----------------------
INC-001 text contains "payments-svc" (as the service field of each event).
INC-002 query text contains "payment-service".
These are different tokens after whitespace splitting, so the Jaccard
similarity drops from the ~1.0 you'd expect for structurally identical
incidents down to ~0.65, falling below a 0.7 match threshold.

Why our engine succeeds
-----------------------
Shape encoding strips service names before hashing → rename-invariant → 1.0.
"""
from __future__ import annotations

from typing import Iterable


class VectorBaselineEngine:
    """Naive token-overlap baseline.  Same interface as adapters.myteam.Engine."""

    _WINDOW = 600.0

    def __init__(self) -> None:
        self._all_events: list[dict] = []
        self._incidents:  dict[str, dict] = {}   # incident_id -> {text, ts}

    # ── Adapter interface ──────────────────────────────────────────────────────

    def ingest(self, events: Iterable[dict]) -> None:
        for event in events:
            self._all_events.append(event)
            if event.get("kind") == "incident_signal":
                self._index_incident(event)

    def reconstruct_context(self, signal: dict, mode: str = "fast") -> dict:
        ts = float(signal.get("ts", 0))
        window = [
            e for e in self._all_events
            if float(e.get("ts", 0)) >= ts - self._WINDOW
            and float(e.get("ts", 0)) <= ts
        ]

        query_text   = self._to_text(window)
        query_tokens = self._tokenise(query_text)

        matches = []
        for iid, data in self._incidents.items():
            inc_tokens = self._tokenise(data["text"])
            union = query_tokens | inc_tokens
            if not union:
                continue
            intersection = query_tokens & inc_tokens
            sim = round(len(intersection) / len(union), 4)
            if sim > 0:
                matches.append({
                    "past_incident_id": iid,
                    "similarity":       sim,
                    "rationale": (
                        f"token overlap {len(intersection)}/{len(union)} "
                        "(service names not normalised — rename-blind)"
                    ),
                })

        matches.sort(key=lambda m: -m["similarity"])
        top_sim = matches[0]["similarity"] if matches else 0.0

        return {
            "related_events":          window[-10:],
            "causal_chain":            [],
            "similar_past_incidents":  matches[:5],
            "suggested_remediations":  [],
            "confidence":              top_sim,
            "explain": (
                "Naive token-overlap baseline (foil). "
                f"Top match: {matches[0]['past_incident_id'] if matches else 'none'} "
                f"sim={top_sim:.3f}. "
                "Service names are NOT normalised — this baseline is rename-blind."
            ),
        }

    def close(self) -> None:
        pass

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _index_incident(self, event: dict) -> None:
        iid = event.get("incident_id") or event.get("id", "")
        if not iid:
            return
        ts = float(event.get("ts", 0))
        window = [
            e for e in self._all_events
            if float(e.get("ts", 0)) >= ts - self._WINDOW
        ]
        self._incidents[iid] = {"text": self._to_text(window), "ts": ts}

    @staticmethod
    def _to_text(events: list[dict]) -> str:
        """Flatten event fields to a string — service names deliberately kept."""
        parts: list[str] = []
        for e in events:
            parts.append(e.get("kind", ""))
            parts.append(e.get("service", ""))          # ← rename blindspot
            if e.get("message"):
                parts.append(e["message"])
            if e.get("metric_name"):
                parts.append(e["metric_name"])
            if e.get("version"):
                parts.append(e["version"])
            if e.get("severity"):
                parts.append(e["severity"])
            if e.get("level"):
                parts.append(e["level"])
        return " ".join(p for p in parts if p)

    @staticmethod
    def _tokenise(text: str) -> set[str]:
        """Whitespace split — keeps 'payments-svc' and 'payment-service' distinct."""
        return set(text.lower().split()) - {""}
