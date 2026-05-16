from __future__ import annotations

from schema import MatchResult, NormalizedEvent, Shape


class ShapeEncoder:
    """Encodes normalized event windows into hashable Shape signatures."""

    def encode(
        self,
        normalized_events: list[NormalizedEvent],
        incident_id: str,
        window_start: float,
        window_end: float,
    ) -> Shape:
        """Build a Shape from a temporally-ordered list of NormalizedEvents."""
        signature = tuple(
            (e.role, e.kind, e.delta_bucket, e.payload_hash)
            for e in normalized_events
        )
        return Shape(
            signature=signature,
            incident_id=incident_id,
            window_start=window_start,
            window_end=window_end,
            event_ids=tuple(e.original_id for e in normalized_events),
        )

    def partial_signatures(
        self, signature: tuple, min_length: int = 2
    ) -> list[tuple]:
        """
        All contiguous sub-sequences of length >= min_length, sorted by length
        descending before the 50-cap is applied.  Explicit sort (vs relying on
        loop order) ensures longer — more discriminative, less collision-prone —
        sub-sequences are always kept when the cap fires.
        """
        n = len(signature)
        all_subs: list[tuple] = [
            signature[start : start + length]
            for length in range(min_length, n + 1)
            for start in range(n - length + 1)
        ]
        all_subs.sort(key=len, reverse=True)
        return all_subs[:50]

    @staticmethod
    def signature_length(signature: tuple) -> int:
        return len(signature)


class ShapeIndex:
    """
    Two-tier inverted index over Shape signatures.

    Tier 1 (_full):    exact full-signature → [incident_id, ...]
    Tier 2 (_partial): contiguous sub-sequence → [(incident_id, full_sig_len), ...]

    Scoring for partial hits:
        score = best_match_length / max(query_length, candidate_length)
    Equivalently: (best_match / candidate_len) * min(1.0, candidate_len / query_len)
    — the second form shows that short candidates are penalised because their
    length_penalty = candidate_len / query_len < 1.0, preventing trivially-short
    signatures from ranking highly.
    Exact matches always score 1.0 and are returned ahead of all partial hits.
    """

    def __init__(self) -> None:
        self._full: dict[tuple, list[str]] = {}
        self._partial: dict[tuple, list[tuple[str, int]]] = {}
        # Tuple-level index: each individual event tuple → set of incident_ids
        # containing it. Used for non-contiguous family matching when contiguous
        # sub-sequence overlap fails (e.g. query has IS event; stored sigs don't).
        self._tuple_index: dict[tuple, set[str]] = {}
        self._shapes_by_incident: dict[str, Shape] = {}
        self._encoder = ShapeEncoder()

    # ── Indexing ──────────────────────────────────────────────────────────────

    def add(self, shape: Shape) -> None:
        """Index a Shape — O(P) where P <= 50 is the partial count."""
        if not shape.signature:
            return
        iid = shape.incident_id
        sig = shape.signature
        sig_len = len(sig)

        self._shapes_by_incident[iid] = shape

        # Tier 1: exact full-signature
        self._full.setdefault(sig, []).append(iid)

        # Tier 2: partial sub-sequences (each append is O(1))
        for partial in self._encoder.partial_signatures(sig):
            self._partial.setdefault(partial, []).append((iid, sig_len))

        # Tier 3: tuple-level (non-contiguous) inverted index
        for tup in sig:
            self._tuple_index.setdefault(tup, set()).add(iid)

    # ── Querying ──────────────────────────────────────────────────────────────

    def query(self, query_signature: tuple, top_k: int = 5) -> list[MatchResult]:
        """
        Returns up to top_k MatchResults ranked by similarity descending.
        Ties broken by incident_id (alphabetical) for reproducibility.
        """
        if not query_signature or len(query_signature) < 2:
            return []

        query_len = len(query_signature)
        results: list[MatchResult] = []
        exact_ids: set[str] = set()

        # ── Tier 1: exact full-signature hit → similarity 1.0 ────────────────
        for iid in self._full.get(query_signature, []):
            shape = self._shapes_by_incident.get(iid)
            if shape:
                results.append(MatchResult(
                    incident_id=iid,
                    similarity=1.0,
                    match_type="full",
                    matched_positions=query_len,
                    shape=shape,
                ))
                exact_ids.add(iid)

        # ── Tier 2: partial sub-sequence lookup ──────────────────────────────
        # Cap: examine the 50 longest unique sub-sequences of the query
        # (same cap applied during add(), so the sets align)
        query_partials = self._encoder.partial_signatures(query_signature)

        # Per candidate: record the longest matching sub-sequence found
        candidate_best: dict[str, int] = {}

        for partial in query_partials:
            hits = self._partial.get(partial)
            if not hits:
                continue
            plen = len(partial)
            for iid, _full_len in hits:
                if iid in exact_ids:
                    continue
                if plen > candidate_best.get(iid, 0):
                    candidate_best[iid] = plen

        for iid, best_len in candidate_best.items():
            shape = self._shapes_by_incident.get(iid)
            if not shape:
                continue
            candidate_len = len(shape.signature)
            # score in [0, 1) for partial hits; 1.0 reserved for exact matches
            score = (best_len ** 1.15) / max(query_len, candidate_len)   # reward longer matches
            results.append(MatchResult(
                incident_id=iid,
                similarity=round(score, 6),
                match_type="partial",
                matched_positions=best_len,
                shape=shape,
            ))

        # ── Tier 3: tuple-level (non-contiguous) candidates ──────────────────
        # Score by Jaccard-like ratio; cap at 0.65 so structural contiguous
        # matches always outrank non-contiguous tuple overlaps.
        query_tuples = set(query_signature)
        already_picked = {r.incident_id for r in results}
        tuple_candidates: dict[str, int] = {}
        for tup in query_tuples:
            for iid in self._tuple_index.get(tup, ()):
                if iid in already_picked:
                    continue
                tuple_candidates[iid] = tuple_candidates.get(iid, 0) + 1

        for iid, shared in tuple_candidates.items():
            shape = self._shapes_by_incident.get(iid)
            if not shape:
                continue
            cand_unique = len(set(shape.signature))
            score = shared / max(len(query_tuples), cand_unique)
            score = min(score, 0.65)
            results.append(MatchResult(
                incident_id=iid,
                similarity=round(score, 6),
                match_type="partial",
                matched_positions=shared,
                shape=shape,
            ))

        # Exact matches (1.0) naturally sort first; ties broken by incident_id
        results.sort(key=lambda r: (-r.similarity, r.incident_id))
        return results[:top_k]

    # ── Conveniences ──────────────────────────────────────────────────────────

    def clear(self) -> None:
        """Reset all indexes — used by the demo's scenario reset button."""
        self._full.clear()
        self._partial.clear()
        self._tuple_index.clear()
        self._shapes_by_incident.clear()

    def __len__(self) -> int:
        return len(self._shapes_by_incident)

    def __contains__(self, incident_id: str) -> bool:
        return incident_id in self._shapes_by_incident
