"""
api/test_api.py — Phase A smoke test.

Usage:
    # Terminal 1:  uvicorn api.server:app --port 8000
    # Terminal 2:  python api/test_api.py
"""
from __future__ import annotations

import asyncio
import json
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import websockets

BASE = "http://localhost:8000"
WS   = "ws://localhost:8000"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _wait_for_server(retries: int = 10, delay: float = 0.5) -> bool:
    for _ in range(retries):
        try:
            r = requests.get(f"{BASE}/health", timeout=2)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(delay)
    return False


def section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print("=" * 60)


# ── REST tests ─────────────────────────────────────────────────────────────────

def test_rest() -> None:
    section("GET /health")
    r = requests.get(f"{BASE}/health")
    print(f"  status={r.status_code}  body={r.json()}")
    assert r.json() == {"status": "ok"}, "health check failed"

    section("GET /scenarios")
    r = requests.get(f"{BASE}/scenarios")
    scenarios = r.json()
    print(json.dumps(scenarios, indent=2))
    assert len(scenarios) >= 2, "expected at least 2 scenarios"

    section("POST /reset")
    r = requests.post(f"{BASE}/reset")
    print(f"  {r.json()}")

    section("GET /state  (after reset — empty)")
    r = requests.get(f"{BASE}/state")
    state = r.json()
    print(json.dumps(state, indent=2))
    assert state["ingested_count"] == 0, "expected empty engine after reset"


# ── WebSocket test ─────────────────────────────────────────────────────────────

async def test_websocket() -> None:
    section("WS /stream/rename_stress?speed=fast  (first 12 messages)")
    uri = f"{WS}/stream/rename_stress?speed=fast"

    async with websockets.connect(uri) as ws:
        count = 0
        incident_resolved_seen = False

        async for raw in ws:
            msg = json.loads(raw)
            mtype = msg["type"]

            if mtype == "event_ingested":
                e     = msg["event"]
                delta = msg.get("state_delta", {})
                print(
                    f"  [{count+1:02d}] event_ingested  "
                    f"kind={e['kind']:<18}  "
                    f"svc={e.get('service', '-'):<20}  "
                    f"delta={json.dumps(delta)}"
                )

            elif mtype == "incident_resolved":
                incident_resolved_seen = True
                sig     = msg["signal"]
                matches = msg["context"]["similar_past_incidents"]
                top     = matches[0] if matches else {}
                print(
                    f"  [{count+1:02d}] incident_resolved  "
                    f"signal={sig['id']}  "
                    f"top_match={top.get('past_incident_id','-')}  "
                    f"sim={top.get('similarity', 0):.3f}"
                )

            elif mtype == "scenario_complete":
                print(f"  [{count+1:02d}] scenario_complete")
                break

            elif mtype == "error":
                print(f"  ERROR: {msg['message']}")
                break

            count += 1
            if count >= 12 and mtype == "event_ingested":
                # Drain remaining events silently, still wait for incident_resolved
                print(f"  ... (truncating event feed, waiting for incident_resolved) ...")
                async for raw2 in ws:
                    msg2 = json.loads(raw2)
                    if msg2["type"] == "incident_resolved":
                        incident_resolved_seen = True
                        matches = msg2["context"]["similar_past_incidents"]
                        top = matches[0] if matches else {}
                        print(
                            f"  [--] incident_resolved  "
                            f"signal={msg2['signal']['id']}  "
                            f"top_match={top.get('past_incident_id','-')}  "
                            f"sim={top.get('similarity',0):.3f}"
                        )
                    elif msg2["type"] == "scenario_complete":
                        print("  [--] scenario_complete")
                        break
                break

        assert incident_resolved_seen, "never received incident_resolved message"


# ── Foil comparison ────────────────────────────────────────────────────────────

def test_foil_comparison() -> None:
    section("Foil vs Engine: rename_stress INC-001 recall")
    from api.foil import VectorBaselineEngine
    from scenario import rename_stress_scenario

    s    = rename_stress_scenario()
    foil = VectorBaselineEngine()
    foil.ingest(s.events)

    signal = s.test_signals[0]
    ctx    = foil.reconstruct_context(signal)

    matches = {m["past_incident_id"]: m["similarity"]
               for m in ctx["similar_past_incidents"]}

    inc001_sim = matches.get("INC-001", 0.0)
    print(f"  Foil similarity for INC-001 : {inc001_sim:.4f}  "
          f"(our engine: 1.0000)")
    print(f"  Foil explain: {ctx['explain']}")
    assert inc001_sim < 1.0, "foil should NOT score 1.0 — it's supposed to be worse"
    print(f"  [OK] foil is deliberately weaker than the real engine")


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Waiting for server at localhost:8000 ...")
    if not _wait_for_server():
        print("ERROR: server did not start. Run: uvicorn api.server:app --port 8000")
        sys.exit(1)

    test_rest()
    asyncio.run(test_websocket())
    test_foil_comparison()

    print("\n" + "=" * 60)
    print("  Phase A smoke test PASSED")
    print("=" * 60)
