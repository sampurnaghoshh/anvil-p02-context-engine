"""Scalability throughput benchmark for the P-02 Context Engine."""
from __future__ import annotations

import random
import time

from engine.core import ContextEngine
from engine.memory import EventMemory
from engine.storage import InMemoryBackend, SQLiteBackend


# ── Event generation ──────────────────────────────────────────────────────────

def generate_events(n: int = 100_000, seed: int = 42) -> list[dict]:
    rng = random.Random(seed)
    services = [f"svc-{i:02d}" for i in range(50)]
    events: list[dict] = []
    ts = 1000.0
    incident_counter = 0
    remediation_counter = 0
    ev_counter = 0

    while len(events) < n:
        roll = rng.random()
        svc = rng.choice(services)
        eid = f"e{ev_counter}"
        ev_counter += 1

        if roll < 0.60:
            events.append({
                "kind": "metric", "id": eid, "service": svc,
                "name": "qps", "metric_name": "qps",
                "value": rng.uniform(50, 500), "ts": ts,
            })
            ts += 0.5

        elif roll < 0.75:
            mn = rng.choice(["latency_p99_ms", "latency_p95_ms"])
            events.append({
                "kind": "metric", "id": eid, "service": svc,
                "name": mn, "metric_name": mn,
                "value": rng.uniform(100, 9000), "ts": ts,
            })
            ts += 0.5

        elif roll < 0.85:
            level = "ERROR" if rng.random() < 0.20 else "INFO"
            events.append({
                "kind": "log", "id": eid, "service": svc,
                "level": level, "message": f"msg-{ev_counter}", "ts": ts,
            })
            ts += 0.5

        elif roll < 0.95:
            events.append({
                "kind": "deploy", "id": eid, "service": svc,
                "version": f"v{ev_counter}", "ts": ts,
            })
            ts += 0.5

        elif roll < 0.99:
            src = rng.choice(services)
            dst = rng.choice([s for s in services if s != src])
            events.append({
                "kind": "topology", "change": "rename",
                "id": eid, "from_": src, "to": dst, "ts": ts,
            })
            ts += 0.5

        else:
            # incident_signal + remediation pair (counts as 2 events)
            iid = f"INC-{incident_counter}"
            outcome = "success" if incident_counter % 2 == 0 else "failure"
            incident_counter += 1
            events.append({
                "kind": "incident_signal", "id": eid,
                "incident_id": iid, "service": svc, "ts": ts,
            })
            ts += 0.5
            if len(events) < n:
                rid = f"r{remediation_counter}"
                remediation_counter += 1
                events.append({
                    "kind": "remediation", "id": rid,
                    "incident_id": iid, "action": "rollback",
                    "service": svc, "outcome": outcome, "ts": ts,
                })
                ts += 0.5

    return events[:n]


# ── Percentile helper ─────────────────────────────────────────────────────────

def pct(data: list[float], p: float) -> float:
    if not data:
        return 0.0
    sd = sorted(data)
    idx = (p / 100.0) * (len(sd) - 1)
    lo, hi = int(idx), min(int(idx) + 1, len(sd) - 1)
    return sd[lo] + (idx - lo) * (sd[hi] - sd[lo])


# ── Ingest timing helpers ─────────────────────────────────────────────────────

def ingest_bulk(engine: ContextEngine, events: list[dict]) -> float:
    t0 = time.perf_counter()
    engine.ingest(events)
    return time.perf_counter() - t0


def ingest_chunked(engine: ContextEngine, events: list[dict], chunk: int = 1000) -> float:
    t0 = time.perf_counter()
    for i in range(0, len(events), chunk):
        engine.ingest(events[i:i + chunk])
    return time.perf_counter() - t0


def ingest_single(engine: ContextEngine, events: list[dict]) -> float:
    t0 = time.perf_counter()
    for ev in events:
        engine.ingest([ev])
    return time.perf_counter() - t0


# ── Print helpers ─────────────────────────────────────────────────────────────

def print_ingest(label: str, elapsed: float, n: int) -> None:
    eps = n / elapsed if elapsed > 0 else float("inf")
    us = elapsed / n * 1_000_000 if n > 0 else 0.0
    status = "OK" if eps >= 1_000 else "BELOW THRESHOLD"
    print(f"  {label:<34}  {elapsed:6.3f}s  {eps:>12,.0f} ev/s  {us:6.2f} µs/ev  {status}")


def print_query(label: str, latencies: list[float]) -> None:
    p95 = pct(latencies, 95)
    status = "OK" if p95 < 2000 else "ABOVE BUDGET"
    print(f"  {label:<34}  "
          f"min={min(latencies):.2f}ms  "
          f"p50={pct(latencies,50):.2f}ms  "
          f"p95={p95:.2f}ms  "
          f"p99={pct(latencies,99):.2f}ms  "
          f"max={max(latencies):.2f}ms  {status}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    N = 100_000

    print(f"Generating {N:,} synthetic events (seed=42)...")
    events = generate_events(N, seed=42)

    kind_counts: dict[str, int] = {}
    last_signal = None
    for e in events:
        k = e.get("kind", "?")
        kind_counts[k] = kind_counts.get(k, 0) + 1
        if k == "incident_signal":
            last_signal = e

    print(f"  Total generated: {len(events):,}")
    for k in sorted(kind_counts):
        print(f"    {k:<20} {kind_counts[k]:>6}  ({kind_counts[k]/len(events)*100:.1f}%)")
    print()

    # ── InMemory: three ingest modes ──────────────────────────────────────────
    print("=" * 75)
    print("InMemoryBackend ingest")
    print("=" * 75)

    e_bulk = ContextEngine()
    t_bulk = ingest_bulk(e_bulk, events)
    print_ingest("(a) bulk — 1 call", t_bulk, len(events))

    e_chunk = ContextEngine()
    t_chunk = ingest_chunked(e_chunk, events, chunk=1000)
    print_ingest("(b) chunked — 1,000-event batches", t_chunk, len(events))

    e_single = ContextEngine()
    t_single = ingest_single(e_single, events)
    print_ingest("(c) single-event loop", t_single, len(events))

    # ── Query latency (bulk engine) ───────────────────────────────────────────
    print()
    print("=" * 75)
    print("reconstruct_context latency — 50 runs on InMemory bulk engine")
    print("=" * 75)
    if last_signal:
        lats: list[float] = []
        for _ in range(50):
            t0 = time.perf_counter()
            e_bulk.reconstruct_context(last_signal, mode="fast")
            lats.append((time.perf_counter() - t0) * 1000)
        print_query(f"signal={last_signal.get('incident_id')}", lats)
    else:
        print("  No incident_signal found.")

    # ── SQLite: bulk ──────────────────────────────────────────────────────────
    print()
    print("=" * 75)
    print("SQLiteBackend ingest — (a) bulk only")
    print("=" * 75)
    e_sqlite = ContextEngine()
    e_sqlite.memory = EventMemory(backend=SQLiteBackend(":memory:"))
    e_sqlite.causal_builder.memory = e_sqlite.memory
    t_sqlite = ingest_bulk(e_sqlite, events)
    print_ingest("(a) bulk — SQLite :memory:", t_sqlite, len(events))

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    print("=" * 75)
    print("SUMMARY")
    print("=" * 75)
    rows = [
        ("InMemory bulk",    t_bulk,   len(events)),
        ("InMemory chunked", t_chunk,  len(events)),
        ("InMemory single",  t_single, len(events)),
        ("SQLite bulk",      t_sqlite, len(events)),
    ]
    for label, elapsed, n in rows:
        eps = n / elapsed if elapsed > 0 else float("inf")
        status = "OK" if eps >= 1_000 else "BELOW THRESHOLD"
        print(f"  {label:<22}  {eps:>12,.0f} ev/s  {status}")
    if last_signal:
        p95_val = pct(lats, 95)
        status = "OK" if p95_val < 2000 else "ABOVE BUDGET"
        print(f"  {'query p95':<22}  {p95_val:>11.2f} ms  {status}")


if __name__ == "__main__":
    main()
