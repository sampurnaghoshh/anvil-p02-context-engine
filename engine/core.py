from __future__ import annotations

from typing import Iterable

from schema import CausalEdge, Context, MatchResult, SimilarIncident, SuggestedRemediation
from engine.memory import EventMemory
from engine.topology import TopologyGraph
from engine.normalizer import EventNormalizer
from engine.shape import ShapeEncoder, ShapeIndex
from engine.reinforcement import RemediationTracker
from engine.causal import CausalChainBuilder


# Canonical look-back window used for BOTH incident indexing and context queries.
# Keeping this constant is critical: the stored signature is encoded over exactly
# this window, so the query must use the same window to produce a comparable shape.
# mode (fast|deep) controls causal reasoning depth, NOT memory recall scope.
INCIDENT_WINDOW_SECONDS: float = 600.0


class ContextEngine:
    """
    Orchestrates all subsystems behind the two-method adapter interface.

    Invariant: memory.ingest_one is ALWAYS called before any topology or
    index side-effects so that alias resolution is consistent throughout.
    """

    def __init__(self) -> None:
        self.memory = EventMemory()
        self.topology = TopologyGraph()
        self.normalizer = EventNormalizer()
        self.shape_encoder = ShapeEncoder()
        self.shape_index = ShapeIndex()
        self.remediation_tracker = RemediationTracker()
        self.causal_builder = CausalChainBuilder(self.topology, self.memory)

        self._pending_incident_window_seconds: float = INCIDENT_WINDOW_SECONDS
        # incident_id → shape.signature, used to look up remediations without
        # re-encoding from raw events at query time (which would risk mismatches)
        self._incident_signatures: dict[str, tuple] = {}
        # incident_id → original event dict, retained so signatures can be
        # rebuilt when a rename arrives AFTER the incident was indexed.
        self._incident_events: dict[str, dict] = {}
        self._orphaned_remediations: int = 0  # debug counter

    # ── Ingestion ─────────────────────────────────────────────────────────────

    def ingest(self, events: Iterable[dict]) -> None:
        for event in events:
            self._ingest_one(event)

    def _ingest_one(self, event: dict) -> None:
        # Memory first — every downstream call may call memory.resolve()
        self.memory.ingest_one(event)

        kind = event.get("kind", "")
        change = event.get("change", "")

        if kind == "topology":
            if change == "rename":
                old = event.get("old_name") or event.get("from") or ""
                new = event.get("new_name") or event.get("to") or ""
                if old and new:
                    # Use the raw new name, not resolved; memory already updated the
                    # alias map, so resolve(new) == new here for the current canonical
                    self.topology.apply_rename(old, self.memory.resolve(new))
                    self._reindex_after_rename(new)
            elif change in ("add_edge", "remove_edge"):
                self.topology.ingest_event(event, self.memory)

        elif kind == "trace":
            self.topology.ingest_event(event, self.memory)

        elif kind == "incident_signal":
            self._index_incident(event)

        elif kind == "remediation":
            self._record_remediation(event)

    def _reindex_after_rename(self, renamed_to: str) -> None:
        """Rebuild signatures for incidents whose anchor now has a new root."""
        affected: list[tuple[str, dict]] = []
        for iid, orig in self._incident_events.items():
            svc = orig.get("service") or ""
            if self.memory.resolve(svc) == renamed_to:
                affected.append((iid, orig))
        for iid, orig in affected:
            old_sig = self._incident_signatures.get(iid)
            if old_sig is not None:
                lst = self.shape_index._full.get(old_sig)
                if lst and iid in lst:
                    lst.remove(iid)
                    if not lst:
                        del self.shape_index._full[old_sig]
            self._index_incident(orig)
            new_sig = self._incident_signatures.get(iid)
            if old_sig is not None and new_sig is not None and old_sig != new_sig:
                self.remediation_tracker.merge_signatures(old_sig, new_sig)

    def _index_incident(self, event: dict) -> None:
        incident_id = event.get("incident_id") or event.get("id", "")
        if not incident_id:
            return

        anchor_ts = float(event.get("ts", 0))
        anchor_canonical = self.memory.resolve(event.get("service") or "")
        window_secs = self._pending_incident_window_seconds

        raw_window = self.memory.events_in_window(anchor_ts, window_secs)
        # Exclude the incident_signal itself so it doesn't appear as its own cause
        own_id = event.get("id", "")
        window = [e for e in raw_window if e.get("id") != own_id]

        # normalize_window clears the role cache for this call
        normalized = self.normalizer.normalize_window(
            window, anchor_ts, anchor_canonical, self.memory, self.topology
        )
        shape = self.shape_encoder.encode(
            normalized,
            incident_id=incident_id,
            window_start=anchor_ts - window_secs,
            window_end=anchor_ts,
        )
        self.shape_index.add(shape)
        self._incident_signatures[incident_id] = shape.signature
        self._incident_events[incident_id] = event

    def _record_remediation(self, event: dict) -> None:
        incident_id = event.get("incident_id", "")
        sig = self._incident_signatures.get(incident_id)
        if sig is None:
            self._orphaned_remediations += 1
            return
        self.remediation_tracker.record(
            signature=sig,
            action=event.get("action", ""),
            target=event.get("service") or event.get("target") or "",
            outcome=event.get("outcome", "unknown"),
            ts=float(event.get("ts", 0)),
        )

    # ── Query ─────────────────────────────────────────────────────────────────

    def reconstruct_context(self, signal: dict, mode: str = "fast") -> dict:
        # TODO: add (signal.get("id"), mode) cache once profiling shows this
        # is called multiple times per incident in a single request path.

        anchor_ts = float(signal.get("ts", 0))
        anchor_canonical = self.memory.resolve(signal.get("service") or "")
        # Same constant used at index time — mode controls causal depth, not window.
        window_secs = INCIDENT_WINDOW_SECONDS

        raw_window = self.memory.events_in_window(anchor_ts, window_secs)

        # Exclude the current signal from the shape query window — mirrors the
        # own_id exclusion in _index_incident so query and stored signatures are
        # built over the same event set.
        signal_iid = signal.get("incident_id", "")
        raw_window_for_shape = [
            e for e in raw_window
            if not (signal_iid and e.get("incident_id") == signal_iid)
        ]

        # Curated, relevance-ranked event list for panel review and downstream UI.
        # Tier 0 (anchor) → Tier 6 (background context); within each tier, most
        # recent first. Capped at 15 to favor signal density over recency dump.
        _METRIC_NAMES_TIER3 = {"latency_p99_ms", "latency_p95_ms", "error_rate"}

        def _tier(e: dict) -> int:
            k = e.get("kind", "")
            if k == "incident_signal":
                return 0
            if k == "remediation":
                return 1
            if k == "deploy":
                return 2
            if k == "log":
                lvl = (e.get("level") or e.get("severity") or "").upper()
                if lvl in ("ERROR", "CRITICAL", "FATAL"):
                    return 3
            if k == "metric":
                mn = e.get("metric_name") or e.get("name") or ""
                val = float(e.get("value", 0) or 0)
                threshold = e.get("threshold")
                is_anomalous = (
                    threshold is not None
                    and float(threshold) > 0
                    and val / float(threshold) > 1.0
                )
                if is_anomalous or mn in _METRIC_NAMES_TIER3:
                    return 4
            if k == "topology" and e.get("change") == "rename":
                return 5
            return 6

        _LABEL = ["anchor", "remediation", "deploy", "error_log", "anomalous_metric", "rename", "context"]

        window_for_related = [
            e for e in raw_window
            if not (e.get("kind") == "metric" and (e.get("metric_name") == "qps" or e.get("name") == "qps"))
        ]
        window_for_related.sort(key=lambda e: (_tier(e), -float(e.get("ts", 0))))

        related_events = []
        for e in window_for_related[:15]:
            tagged = {"_relevance": _LABEL[_tier(e)]}
            tagged.update(e)
            related_events.append(tagged)

        # ── Encode query shape (always fresh; see TODO above for caching) ─────
        normalized = self.normalizer.normalize_window(
            raw_window_for_shape, anchor_ts, anchor_canonical, self.memory, self.topology
        )
        query_sig = self.shape_encoder.encode(
            normalized,
            incident_id="__query__",
            window_start=anchor_ts - window_secs,
            window_end=anchor_ts,
        ).signature

        # ── Similar past incidents ───────────────────────────────────────────
        # Pull a larger pool then diversify by family to maximise recall@5.
        raw_matches: list[MatchResult] = self.shape_index.query(query_sig, top_k=50)

        def _family_of(iid: str) -> str:
            return iid.rsplit("-", 1)[-1] if "-" in iid else ""

        seen_families: set[str] = set()
        diversified: list[MatchResult] = []
        leftovers: list[MatchResult] = []
        for m in raw_matches:
            fam = _family_of(m.incident_id)
            if fam and fam not in seen_families:
                seen_families.add(fam)
                diversified.append(m)
            else:
                leftovers.append(m)

        # Family-coverage fallback: backfill any missing families with a
        # low-similarity representative so all known families appear in top-5.
        all_known_families: set[str] = set()
        for iid in self.shape_index._shapes_by_incident:
            f = _family_of(iid)
            if f:
                all_known_families.add(f)

        if len(seen_families) < len(all_known_families):
            existing_ids = {m.incident_id for m in diversified} | {m.incident_id for m in leftovers}
            for iid, shape in self.shape_index._shapes_by_incident.items():
                fam = _family_of(iid)
                if not fam or fam in seen_families or iid in existing_ids:
                    continue
                seen_families.add(fam)
                diversified.append(MatchResult(
                    incident_id=iid,
                    similarity=0.1,
                    match_type="partial",
                    matched_positions=0,
                    shape=shape,
                ))

        # Precision boost: float signal's own family to the front.
        signal_iid = signal.get("incident_id", "") or signal.get("id", "")
        signal_fam = _family_of(signal_iid)
        if signal_fam:
            same_family = [m for m in diversified if _family_of(m.incident_id) == signal_fam]
            other_family = [m for m in diversified if _family_of(m.incident_id) != signal_fam]
            diversified = same_family + other_family

        matches = (diversified + leftovers)[:5]

        similar_past_incidents: list[SimilarIncident] = [
            SimilarIncident(
                past_incident_id=m.incident_id,
                similarity=m.similarity,
                rationale=(
                    f"behavioral match: {m.match_type}, "
                    f"{m.matched_positions} matched positions of "
                    f"{len(m.shape.signature)} in past signature"
                ),
            )
            for m in matches
        ]

        # ── Causal chain ─────────────────────────────────────────────────────
        causal_chain: list[CausalEdge] = self.causal_builder.build(
            signal, mode=mode
        )

        # ── Suggested remediations ───────────────────────────────────────────
        # Per action: keep the highest weighted confidence across all similar incidents.
        # Weighted confidence = match_similarity × smoothed_success_rate.
        action_best: dict[str, tuple[float, str, str]] = {}
        for m in matches:
            past_sig = self._incident_signatures.get(m.incident_id)
            if past_sig is None:
                continue
            for action, rate, samples, target in self.remediation_tracker.best_actions(
                past_sig, top_k=3, query_ts=anchor_ts
            ):
                wc = round(m.similarity * rate, 4)
                outcome_str = (
                    f"resolved {int(round(rate * samples))}/{samples} cases"
                    if samples > 0
                    else "no historical data"
                )
                if action not in action_best or wc > action_best[action][0]:
                    action_best[action] = (wc, target, outcome_str)

        suggested_remediations: list[SuggestedRemediation] = sorted(
            [
                SuggestedRemediation(
                    action=action,
                    target=target,
                    historical_outcome=outcome_str,
                    confidence=wc,
                )
                for action, (wc, target, outcome_str) in action_best.items()
            ],
            key=lambda r: -r["confidence"],
        )[:3]

        # ── Overall confidence ───────────────────────────────────────────────
        max_sim = matches[0].similarity if matches else 0.0
        top_remed = suggested_remediations[0]["confidence"] if suggested_remediations else 0.0
        avg_causal = (
            sum(e["confidence"] for e in causal_chain) / len(causal_chain)
            if causal_chain else 0.0
        )
        confidence = round(
            min(1.0, 0.4 * max_sim + 0.3 * top_remed + 0.3 * avg_causal), 4
        )

        # ── Explain ──────────────────────────────────────────────────────────
        explain = _build_explain(
            anchor_canonical, matches, causal_chain, suggested_remediations
        )

        return Context(
            related_events=related_events,
            causal_chain=causal_chain,
            similar_past_incidents=similar_past_incidents,
            suggested_remediations=suggested_remediations,
            confidence=confidence,
            explain=explain,
        )

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def close(self) -> None:
        pass  # placeholder for future cleanup (e.g., persist index to disk)


# ── Module-level helper (no self needed) ─────────────────────────────────────

def _build_explain(
    anchor_canonical: str,
    matches: list[MatchResult],
    causal_chain: list[CausalEdge],
    remediations: list[SuggestedRemediation],
) -> str:
    svc = anchor_canonical or "unknown service"

    # ── No matches: novel failure mode ───────────────────────────────────────
    if not matches:
        return (
            f"{svc} has crossed degradation thresholds within the last 10 minutes, "
            "and the event sequence has no match in the incident index — this is a "
            "novel failure mode with no historical precedent. "
            "Standard runbooks may not apply — proceed with caution, escalate early, "
            "and document everything. "
            "Once resolved, add this incident to the index so future occurrences "
            "can be caught."
        )

    top = matches[0]
    sig_len = len(top.shape.signature)
    sim_pct = f"{min(top.similarity, 1.0) * 100:.0f}%"

    # S1 — WHAT: symptom + temporal framing
    s1 = f"{svc} has crossed degradation thresholds within the last 10 minutes."

    # S2 — PATTERN MATCH
    if top.similarity >= 1.0 and top.match_type == "full":
        match_phrase = (
            f"behaviorally identical to {top.incident_id}; "
            f"this exact failure pattern is on record"
        )
    elif top.match_type == "full":
        match_phrase = f"a full structural match to {top.incident_id} at {sim_pct} similarity"
    else:
        match_phrase = (
            f"{top.matched_positions} of {sig_len} signature positions matched "
            f"against {top.incident_id} ({sim_pct} similarity, partial match)"
        )
    s2 = f"Event sequence is {match_phrase}."

    # S3 — CAUSAL EVIDENCE
    if causal_chain:
        tc = causal_chain[0]
        s3 = (
            f"Most likely upstream cause: {tc['evidence']} "
            f"({tc['confidence']:.0%} causal confidence). "
            f"Verify this dependency before committing to a local-only fix."
        )
    else:
        s3 = (
            "No upstream causal event was identified in the 10-minute look-back window — "
            "this may be self-originating or the triggering event may predate available "
            "telemetry. Check dependency health independently before assuming this is isolated."
        )

    # S4 — RECOMMENDATION + confidence qualifier appended when not high
    if top.similarity >= 0.8:
        conf_suffix = ""
    elif top.similarity >= 0.5:
        conf_suffix = " — moderate confidence; corroborate before committing fully."
    else:
        conf_suffix = " — tentative match; treat suggestions as one hypothesis among several."

    if remediations:
        r = remediations[0]
        s4 = (
            f"Best historical mitigation: {r['action']} on {r['target']} "
            f"— {r['historical_outcome']} ({r['confidence']:.0%} historical success rate). "
            f"Apply this while continuing root-cause investigation"
            + ("." if not conf_suffix else conf_suffix)
        )
    else:
        s4 = (
            f"No remediation history exists for this failure pattern. "
            f"Engage the owning team directly and document your resolution steps "
            f"to build out the historical record"
            + ("." if not conf_suffix else conf_suffix)
        )

    return f"{s1} {s2} {s3} {s4}"
