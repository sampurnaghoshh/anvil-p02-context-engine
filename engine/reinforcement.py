from __future__ import annotations

import math


class RemediationTracker:
    """
    Bayesian-smoothed success-rate tracker keyed by (signature, action).

    Smoothing: rate = (success + α) / (success + failure + α + β)
    With α=β=1 (default), a 1/1 raw rate → 2/3 ≈ 0.67,
    while 9/10 → 10/12 ≈ 0.83 — small samples are appropriately discounted.
    Unknown outcomes are recorded but excluded from the rate denominator.
    smoothed_rate_at() applies exponential time-decay before the Beta prior.
    """

    def __init__(self) -> None:
        # signature → action → {"success", "failure", "unknown", "last_seen_ts",
        #                        "success_ts": list[float], "failure_ts": list[float]}
        self._stats: dict[tuple, dict[str, dict]] = {}
        # signature → action → target_service → count
        self._action_targets: dict[tuple, dict[str, dict[str, int]]] = {}

    # ── Recording ─────────────────────────────────────────────────────────────

    def record(
        self,
        signature: tuple,
        action: str,
        target: str,
        outcome: str,
        ts: float,
    ) -> None:
        """Increment outcome counter and update target tallies."""
        if outcome not in ("success", "failure", "unknown"):
            outcome = "unknown"

        act = self._stats.setdefault(signature, {}).setdefault(
            action,
            {"success": 0, "failure": 0, "unknown": 0, "last_seen_ts": 0.0,
             "success_ts": [], "failure_ts": []},
        )
        act[outcome] += 1
        act["last_seen_ts"] = max(act["last_seen_ts"], ts)
        if outcome == "success":
            act["success_ts"].append(ts)
        elif outcome == "failure":
            act["failure_ts"].append(ts)

        tgt_map = (
            self._action_targets.setdefault(signature, {}).setdefault(action, {})
        )
        tgt_map[target] = tgt_map.get(target, 0) + 1

    # ── Querying ──────────────────────────────────────────────────────────────

    def success_rate(
        self,
        signature: tuple,
        action: str,
        alpha: float = 1.0,
        beta: float = 1.0,
    ) -> tuple[float, int]:
        """
        Returns (smoothed_rate, total_samples).
        total_samples = success + failure (unknown excluded from denominator).
        """
        act = self._stats.get(signature, {}).get(action, {})
        s = act.get("success", 0)
        f = act.get("failure", 0)
        rate = (s + alpha) / (s + f + alpha + beta)
        return (rate, s + f)

    def smoothed_rate_at(
        self,
        signature: tuple,
        action: str,
        query_ts: float,
        half_life_seconds: float = 86400 * 30,
    ) -> float:
        """Time-decayed Beta(1,1)-smoothed success rate.

        Each historical outcome is weighted by exp(-ln(2) * age / half_life).
        Recent outcomes dominate; old ones decay smoothly. With default
        30-day half-life, an outcome from 30 days ago counts as 0.5, from
        60 days ago as 0.25, etc.
        """
        entry = self._stats.get(signature, {}).get(action)
        if not entry:
            return 0.5  # Beta(1,1) prior with no evidence

        decay_const = math.log(2) / half_life_seconds if half_life_seconds > 0 else 0.0

        def weight(ts: float) -> float:
            age = max(0.0, query_ts - ts)
            return math.exp(-decay_const * age) if decay_const > 0 else 1.0

        w_success = sum(weight(ts) for ts in entry.get("success_ts", []))
        w_failure = sum(weight(ts) for ts in entry.get("failure_ts", []))

        # Beta(1,1) priors applied to weighted counts
        return (w_success + 1.0) / (w_success + w_failure + 2.0)

    def best_actions(
        self,
        signature: tuple,
        top_k: int = 3,
        query_ts: float | None = None,
        half_life_seconds: float = 86400 * 30,
    ) -> list[tuple[str, float, int, str]]:
        """
        Returns [(action, smoothed_rate, sample_size, most_common_target), ...]
        sorted by (rate desc, sample_size desc) for tie-breaking.
        When query_ts is provided, rates are time-decayed via smoothed_rate_at.
        """
        sig_stats = self._stats.get(signature, {})
        sig_targets = self._action_targets.get(signature, {})

        rows: list[tuple[str, float, int, str]] = []
        for action in sig_stats:
            if query_ts is not None:
                rate = self.smoothed_rate_at(signature, action, query_ts, half_life_seconds)
                _, samples = self.success_rate(signature, action)
            else:
                rate, samples = self.success_rate(signature, action)
            tgt_map = sig_targets.get(action, {})
            best_target = max(tgt_map, key=lambda t: tgt_map[t]) if tgt_map else ""
            rows.append((action, rate, samples, best_target))

        rows.sort(key=lambda x: (-x[1], -x[2]))
        return rows[:top_k]

    # ── Merging ───────────────────────────────────────────────────────────────

    def merge_signatures(self, signature_a: tuple, signature_b: tuple) -> None:
        """
        Merge all stats from signature_b into signature_a, then remove signature_b.
        Use when a rename makes two previously-distinct signatures equivalent,
        so their remediation histories are consolidated under one canonical key.
        """
        stats_b = self._stats.pop(signature_b, {})
        targets_b = self._action_targets.pop(signature_b, {})

        a_stats = self._stats.setdefault(signature_a, {})
        a_targets = self._action_targets.setdefault(signature_a, {})

        for action, counts_b in stats_b.items():
            if action not in a_stats:
                a_stats[action] = dict(counts_b)
                a_stats[action]["success_ts"] = list(counts_b.get("success_ts", []))
                a_stats[action]["failure_ts"] = list(counts_b.get("failure_ts", []))
            else:
                ca = a_stats[action]
                ca["success"] += counts_b.get("success", 0)
                ca["failure"] += counts_b.get("failure", 0)
                ca["unknown"] += counts_b.get("unknown", 0)
                ca["last_seen_ts"] = max(
                    ca["last_seen_ts"], counts_b.get("last_seen_ts", 0.0)
                )
                ca.setdefault("success_ts", []).extend(counts_b.get("success_ts", []))
                ca.setdefault("failure_ts", []).extend(counts_b.get("failure_ts", []))

        for action, tgt_b in targets_b.items():
            tgt_a = a_targets.setdefault(action, {})
            for target, count in tgt_b.items():
                tgt_a[target] = tgt_a.get(target, 0) + count

    # ── Maintenance ───────────────────────────────────────────────────────────

    def clear(self) -> None:
        self._stats.clear()
        self._action_targets.clear()
