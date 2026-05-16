from __future__ import annotations

import hashlib
import re
from typing import TYPE_CHECKING

from schema import NormalizedEvent

if TYPE_CHECKING:
    from engine.memory import EventMemory
    from engine.topology import TopologyGraph

_VOLATILE_RE = re.compile(
    r"\b(?:"
    r"v\d+(?:\.\d+){1,3}"
    r"|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    r"|\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?::\d+)?"
    r"|[a-f0-9]{32,}"
    r"|\d+"
    r")\b",
    re.IGNORECASE,
)

# Strips cascading rename suffixes (-r3, -r3-r7, etc.) from service names
# embedded in log messages. Must run BEFORE _VOLATILE_RE because the digits
# in "-r3" are not standalone word tokens and are invisible to \b\d+\b.
_RENAME_SUFFIX_RE = re.compile(r"(?:-r\d+)+", re.IGNORECASE)

_DELTA_BOUNDS: list[tuple[float, int]] = [
    (-120.0, -3), (-30.0, -2), (-5.0, -1),
    (5.0, 0), (30.0, 1), (120.0, 2),
]

def _delta_bucket(delta_s: float) -> int:
    for bound, bucket in _DELTA_BOUNDS:
        if delta_s <= bound:
            return bucket
    return 3

def _scrub(text: str, service_name: str) -> str:
    if service_name:
        text = text.replace(service_name, "_SVC_")
    text = _RENAME_SUFFIX_RE.sub("", text)
    return _VOLATILE_RE.sub("_", text).strip()

def _payload_hash(kind: str, event: dict, canonical_service: str) -> str:
    parts = [kind]
    if kind == "log":
        parts.append(event.get("level", ""))
        parts.append(_scrub(event.get("message", ""), canonical_service))
    elif kind == "metric":
        name = event.get("metric_name", "")
        val = float(event.get("value") or 0.0)
        thresh = event.get("threshold")
        if thresh:
            ratio = val / float(thresh)
            bracket = "CRITICAL" if ratio > 1.8 else "HIGH" if ratio > 1.0 else "NORMAL"
        else:
            bracket = "_"
        parts += [name, bracket]
    elif kind == "deploy":
        parts.append("deploy")
    elif kind == "trace":
        parts.append(event.get("status", ""))
        dur = float(event.get("duration_ms") or 0.0)
        latency = "CRITICAL" if dur > 5000 else "SLOW" if dur > 1000 else "OK"
        parts.append(latency)
    elif kind == "topology":
        parts.append(event.get("change", ""))
    elif kind == "incident_signal":
        parts.append(event.get("severity", ""))
        parts.append(_scrub(event.get("description", ""), canonical_service))
    elif kind == "remediation":
        parts.append(_scrub(event.get("action", ""), canonical_service))
    return hashlib.md5("|".join(parts).encode()).hexdigest()[:12]

def _is_incident_relevant(event: dict) -> bool:
    """Mild filter — keeps causal signal while dropping most noise."""
    kind = event.get("kind", "")
    if kind in ("incident_signal", "deploy", "remediation"):
        return True
    if kind == "topology":
        return event.get("change") == "rename"
    if kind == "log":
        level = (event.get("level") or "").upper()
        return level in ("ERROR", "CRITICAL", "FATAL")
    if kind == "metric":
        thresh = event.get("threshold")
        if thresh is None:
            return False
        try:
            return float(event.get("value") or 0) > float(thresh) * 1.3
        except:
            return False
    if kind == "trace":
        return False
    return False

class EventNormalizer:
    def normalize_event(
        self,
        event: dict,
        anchor_ts: float,
        anchor_canonical: str,
        memory: "EventMemory",
        topology: "TopologyGraph",
    ) -> NormalizedEvent:
        canonical = memory.resolve(event.get("service") or "")
        role = topology.role_of(canonical, anchor_canonical) if canonical else "unknown"
        return NormalizedEvent(
            original_id=event.get("id", ""),
            kind=event.get("kind", ""),
            ts=event["ts"],
            role=role,
            canonical_service=canonical,
            delta_bucket=_delta_bucket(event["ts"] - anchor_ts),
            payload_hash=_payload_hash(event.get("kind", ""), event, canonical),
        )

    def normalize_window(
        self,
        events: list[dict],
        anchor_ts: float,
        anchor_canonical: str,
        memory: "EventMemory",
        topology: "TopologyGraph",
    ) -> list[NormalizedEvent]:
        topology.clear_role_cache()
        # Filter + sort
        relevant = [e for e in events if _is_incident_relevant(e)]
        return [
            self.normalize_event(e, anchor_ts, anchor_canonical, memory, topology)
            for e in sorted(relevant, key=lambda e: e["ts"])
        ]