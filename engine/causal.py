from __future__ import annotations

from schema import CausalEdge
from engine.memory import EventMemory
from engine.topology import TopologyGraph

_FAST_WINDOW = 600.0
_DEEP_WINDOW = 1800.0
_FAST_MIN_CONF = 0.4
_DEEP_MIN_CONF = 0.3
_MAX_EDGES = 10

# Confidence weight for (cause_kind, effect_kind) pairs.
# Only these pairs produce edges; anything else is ignored.
_KIND_WEIGHT: dict[tuple[str, str], float] = {
    ("deploy",  "incident_signal"): 0.8,
    ("deploy",  "log"):             0.9,
    ("deploy",  "metric"):          0.7,
    ("metric",  "log"):             0.6,
    ("metric",  "incident_signal"): 0.5,
}


def _topology_weight(
    topology: TopologyGraph,
    cause_svc: str,
    effect_svc: str,
    max_hops: int,
) -> float:
    """
    Returns 1.0 / 0.7 / 0.4 / 0.0 based on hop distance from cause to effect
    in the directed call graph.  0.0 means no path → edge is dropped.
    """
    if cause_svc == effect_svc:
        return 1.0
    if effect_svc in topology.descendants(cause_svc, max_hops=1):
        return 0.7
    if max_hops >= 2 and effect_svc in topology.descendants(cause_svc, max_hops=2):
        return 0.4
    return 0.0


def _is_anomalous(event: dict) -> bool:
    """Metric is anomalous if value > threshold; if no threshold present, include anyway."""
    thresh = event.get("threshold")
    if thresh is None:
        return True
    try:
        return float(event.get("value") or 0) > float(thresh)
    except (TypeError, ValueError):
        return True


def _is_error_log(event: dict) -> bool:
    level = (event.get("level") or "").upper()
    return not level or level in ("ERROR", "CRITICAL", "FATAL")


def _hop_label(topo_w: float) -> str:
    if topo_w == 1.0:
        return "same-service"
    if topo_w == 0.7:
        return "1-hop downstream"
    return "2-hop downstream"


def _evidence(
    cause: dict,
    effect: dict,
    cause_svc: str,
    effect_svc: str,
    anchor_ts: float,
    topo_w: float,
) -> str:
    cause_rel = int(cause.get("ts", 0) - anchor_ts)
    effect_rel = int(effect.get("ts", 0) - anchor_ts)
    gap = int(effect.get("ts", 0) - cause.get("ts", 0))
    ckind = cause.get("kind", "event")
    ekind = effect.get("kind", "event")
    if ekind == "log":
        lvl = (effect.get("level") or "").upper()
        if lvl:
            ekind = f"{lvl} {ekind}"
    return (
        f"{ckind} on {cause_svc} at t={cause_rel:+d}s "
        f"preceded {ekind} on {effect_svc} at t={effect_rel:+d}s "
        f"({gap}s gap, {_hop_label(topo_w)})"
    )


class CausalChainBuilder:

    def __init__(self, topology: TopologyGraph, memory: EventMemory) -> None:
        self._topology = topology
        self._memory = memory

    def build(
        self,
        anchor_event: dict,
        window_seconds: float = 600.0,
        mode: str = "fast",
    ) -> list[CausalEdge]:
        if mode == "deep":
            window_seconds = _DEEP_WINDOW
            max_hops = 2
            min_conf = _DEEP_MIN_CONF
        else:
            window_seconds = _FAST_WINDOW
            max_hops = 1
            min_conf = _FAST_MIN_CONF

        anchor_ts = float(anchor_event.get("ts", 0))
        anchor_canonical = self._memory.resolve(anchor_event.get("service") or "")

        window = self._memory.events_in_window(anchor_ts, window_seconds)

        # ── Scope candidate sets to relevant services ─────────────────────────
        # Causes come from the anchor's service or any upstream caller.
        # Effects are symptoms on the anchor's service or anything it calls.
        upstream = {anchor_canonical} | self._topology.ancestors(
            anchor_canonical, max_hops=max_hops
        )
        downstream = {anchor_canonical} | self._topology.descendants(
            anchor_canonical, max_hops=max_hops
        )

        causes: list[dict] = []
        effects: list[dict] = []

        for e in window:
            svc = self._memory.resolve(e.get("service") or "")
            kind = e.get("kind", "")
            ets = float(e.get("ts", 0))

            if ets < anchor_ts:  # causes must precede anchor
                if kind == "deploy" and svc in upstream:
                    causes.append(e)
                elif kind == "metric" and _is_anomalous(e) and svc in upstream:
                    causes.append(e)

            # Effects can be at or before anchor ts; metrics also qualify as effects
            if kind == "incident_signal" and svc in downstream:
                effects.append(e)
            elif kind == "log" and _is_error_log(e) and svc in downstream:
                effects.append(e)
            elif kind == "metric" and _is_anomalous(e) and svc in downstream:
                effects.append(e)

        # ── Build causal edges ────────────────────────────────────────────────
        edges: list[CausalEdge] = []

        for cause in causes:
            cause_ts = float(cause.get("ts", 0))
            cause_svc = self._memory.resolve(cause.get("service") or "")
            cause_kind = cause.get("kind", "")
            if not cause_svc:
                continue

            for effect in effects:
                effect_ts = float(effect.get("ts", 0))

                if effect_ts <= cause_ts:
                    continue
                if effect_ts - cause_ts > window_seconds:
                    continue

                effect_svc = self._memory.resolve(effect.get("service") or "")
                if not effect_svc:
                    continue

                topo_w = _topology_weight(
                    self._topology, cause_svc, effect_svc, max_hops
                )
                if topo_w == 0.0:
                    continue

                kw = _KIND_WEIGHT.get((cause_kind, effect.get("kind", "")), 0.0)
                if kw == 0.0:
                    continue

                time_prox = 1.0 - min(1.0, (effect_ts - cause_ts) / window_seconds)
                confidence = round(time_prox * topo_w * kw, 4)

                if confidence < min_conf:
                    continue

                edges.append(CausalEdge(
                    cause_id=cause.get("id", ""),
                    effect_id=effect.get("id", ""),
                    evidence=_evidence(
                        cause, effect, cause_svc, effect_svc, anchor_ts, topo_w
                    ),
                    confidence=confidence,
                ))

        edges.sort(key=lambda e: -e["confidence"])
        return edges[:_MAX_EDGES]
