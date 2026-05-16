"""
BenchMapper — verbatim extraction of the translation logic from
bench-p02-context/adapters/myteam.py.

Translates raw harness event dicts into engine-native field names
(and back on the output side). No logic changes from the original;
only the form changes (class methods instead of module functions,
counter as an instance variable instead of a module-level list).
"""
from __future__ import annotations

from datetime import datetime


class BenchMapper:
    """
    Translates between the bench harness schema and the engine schema.

    Mismatch table (verbatim from adapters/myteam.py docstring):
      ts format       harness: ISO string  →  engine: float (Unix epoch)
      rename source   harness: from_       →  engine: old_name
      rename target   harness: to          →  engine: new_name
      topo change     harness: dep_add / dep_remove  →  engine: add_edge / remove_edge
      topo src/dst    harness: from_, to   →  engine: edge_source, edge_target
      log body        harness: msg         →  engine: message
      metric name     harness: name        →  engine: metric_name
      incident match  harness: incident_id →  engine: past_incident_id  (output side)
      CausalEdge keys harness: cause_event_id / effect_event_id  →  engine: cause_id / effect_id
    """

    def __init__(self) -> None:
        # Mutable single-element list mirrors the original module-level _event_counter.
        self._counter: list[int] = [0]

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _iso_to_float(ts) -> float:
        if isinstance(ts, (int, float)):
            return float(ts)
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            return dt.timestamp()
        except (ValueError, AttributeError, TypeError):
            return 0.0

    # ── Protocol methods ──────────────────────────────────────────────────────

    def map_event(self, e: dict) -> dict | None:
        out = dict(e)
        if "ts" in out:
            out["ts"] = self._iso_to_float(out["ts"])
        if "id" not in out:
            self._counter[0] += 1
            out["id"] = f"__syn_{self._counter[0]}"
        kind   = out.get("kind", "")
        change = out.get("change", "")

        # Drop background qps noise — high-frequency, zero causal signal,
        # floods signatures with identically-hashed tuples.
        if kind == "metric" and (out.get("name") == "qps" or out.get("metric_name") == "qps"):
            return None

        if kind == "topology":
            from_ = out.get("from_", "")
            to    = out.get("to", "")
            if change == "rename":
                out["old_name"] = from_
                out["new_name"] = to
            elif change == "dep_add":
                out["change"]       = "add_edge"
                out["edge_source"]  = from_
                out["edge_target"]  = to
            elif change == "dep_remove":
                out["change"]       = "remove_edge"
                out["edge_source"]  = from_
                out["edge_target"]  = to
        elif kind == "log":
            if "msg" in out and "message" not in out:
                out["message"] = out["msg"]
        elif kind == "metric":
            if "name" in out and "metric_name" not in out:
                out["metric_name"] = out["name"]
        return out

    def map_signal(self, raw: dict) -> dict:
        result = self.map_event(raw)
        # Signals are never qps metrics; fallback preserves type contract.
        return result if result is not None else dict(raw)

    def unmap_context(self, ctx: dict) -> dict:
        out = dict(ctx)
        translated_incidents = []
        for inc in out.get("similar_past_incidents", []):
            inc2 = dict(inc)
            if "past_incident_id" in inc2 and "incident_id" not in inc2:
                inc2["incident_id"] = inc2.pop("past_incident_id")
            translated_incidents.append(inc2)
        out["similar_past_incidents"] = translated_incidents
        translated_chain = []
        for edge in out.get("causal_chain", []):
            e2 = dict(edge)
            if "cause_id" in e2:
                e2["cause_event_id"] = e2.pop("cause_id")
            if "effect_id" in e2:
                e2["effect_event_id"] = e2.pop("effect_id")
            translated_chain.append(e2)
        out["causal_chain"] = translated_chain
        return out
