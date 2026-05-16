from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypedDict

# ── Literal type aliases ──────────────────────────────────────────────────────

EventKind = Literal[
    "deploy", "log", "metric", "trace",
    "topology", "incident_signal", "remediation",
]
Role = Literal["target", "upstream", "downstream", "peripheral", "unknown"]
MatchType = Literal["full", "partial"]
Mode = Literal["fast", "deep"]

# ── TypedDicts: external / spec-facing ────────────────────────────────────────

class _EventRequired(TypedDict):
    id: str
    kind: str    # EventKind
    ts: float    # Unix epoch seconds


class Event(_EventRequired, total=False):
    service: str
    # deploy
    version: str
    # log
    message: str
    level: str           # "ERROR" | "WARN" | "INFO"
    # metric
    metric_name: str
    value: float
    threshold: float
    # trace
    span_id: str
    parent_span_id: str
    trace_id: str
    duration_ms: float
    status: str          # "ok" | "error"
    # topology
    change: str          # "rename" | "add_edge" | "remove_edge"
    old_name: str        # rename: previous service name
    new_name: str        # rename: new canonical service name
    edge_source: str     # add/remove edge: source service
    edge_target: str     # add/remove edge: target service
    # incident_signal
    incident_id: str
    severity: str
    description: str
    # remediation
    action: str
    actor: str
    outcome: str         # "success" | "failure" | "unknown"
    duration_s: float


class CausalEdge(TypedDict):
    cause_id: str
    effect_id: str
    evidence: str
    confidence: float


class SimilarIncident(TypedDict):
    past_incident_id: str
    similarity: float
    rationale: str


class SuggestedRemediation(TypedDict):
    action: str
    target: str
    historical_outcome: str
    confidence: float


class Context(TypedDict):
    related_events: list[dict]
    causal_chain: list[CausalEdge]
    similar_past_incidents: list[SimilarIncident]
    suggested_remediations: list[SuggestedRemediation]
    confidence: float
    explain: str


# ── Dataclasses: internal engine types ───────────────────────────────────────

@dataclass(frozen=True)
class NormalizedEvent:
    original_id: str
    kind: str
    ts: float
    role: str            # Role literal
    canonical_service: str
    delta_bucket: int    # signed seconds from anchor event, quantised to bucket
    payload_hash: str    # hash of kind + normalised payload fields


@dataclass(frozen=True)
class Shape:
    """Hashable behavioral signature for one incident window."""
    signature: tuple          # ((role, kind, delta_bucket, payload_hash), ...)
    incident_id: str
    window_start: float
    window_end: float
    event_ids: tuple          # (str, ...) — ordered by ts


@dataclass
class MatchResult:
    incident_id: str
    similarity: float         # 0.0 – 1.0
    match_type: str           # MatchType literal
    matched_positions: int
    shape: Shape
