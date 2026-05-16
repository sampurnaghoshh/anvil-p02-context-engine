"""
api/server.py — FastAPI wrapper around adapters.myteam.Engine.

Endpoints
---------
GET  /health
GET  /scenarios
POST /reset
GET  /state
WS   /stream/{scenario_name}?speed=fast|normal|slow
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

# Make project root importable regardless of working directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from adapters.myteam import Engine
from scenario import Scenario, all_scenarios

# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(title="Anvil P-02 Context Engine API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Module-level state (single engine; demo assumes one client) ────────────────

_engine: Optional[Engine] = None
_SCENARIOS: dict[str, Scenario] = {s.name: s for s in all_scenarios()}

_SPEED_DELAY = {"fast": 0.05, "normal": 0.30, "slow": 0.80}


def _get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = Engine()
    return _engine


def _reset() -> None:
    global _engine
    if _engine is not None:
        try:
            _engine.close()
        except Exception:
            pass
    _engine = Engine()


# ── Serialisation helpers ──────────────────────────────────────────────────────

def _ser(obj: Any) -> Any:
    """Recursively convert tuples -> lists so JSON serialisation never fails."""
    if isinstance(obj, tuple):
        return [_ser(x) for x in obj]
    if isinstance(obj, list):
        return [_ser(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _ser(v) for k, v in obj.items()}
    return obj


# ── Engine state introspection ─────────────────────────────────────────────────

def _read_state() -> dict:
    eng = _get_engine()
    ce = eng._engine                       # ContextEngine (internal; read-only)
    g  = ce.topology._g
    mem = ce.memory

    _aliases = mem.all_aliases()
    services = sorted(
        set(g.nodes())
        | set(_aliases.values())
    )
    topology_edges = [list(e) for e in g.edges()]
    renames = {k: v for k, v in _aliases.items() if k != v}

    return {
        "services":          services,
        "topology_edges":    topology_edges,
        "ingested_count":    len(mem),
        "incidents_indexed": list(ce._incident_signatures.keys()),
        "renames":           renames,
    }


def _state_delta(
    event:          dict,
    eng:            Engine,
    edges_before:   set,
    edges_after:    set,
    inc_before:     set,
    inc_after:      set,
) -> dict:
    """Return a minimal dict describing what changed after ingesting `event`."""
    kind   = event.get("kind", "")
    change = event.get("change", "")
    ce     = eng._engine

    # Rename is detected from the event fields (edge set changes too, but rename
    # is the semantically important signal for the frontend animation).
    if kind == "topology" and change == "rename":
        return {
            "renamed": {
                "from": event.get("old_name", ""),
                "to":   event.get("new_name", ""),
            }
        }

    new_edges    = edges_after - edges_before
    new_incidents = inc_after - inc_before

    if kind == "topology" and change == "add_edge":
        # Use resolved names if available; fall back to event fields.
        if new_edges:
            src, dst = next(iter(new_edges))
        else:
            src = ce.memory.resolve(event.get("edge_source") or event.get("source") or "")
            dst = ce.memory.resolve(event.get("edge_target") or event.get("target") or "")
        return {"edge_added": [src, dst]}

    if kind == "trace" and new_edges:
        src, dst = next(iter(new_edges))
        return {"edge_inferred": [src, dst]}

    if kind == "incident_signal" and new_incidents:
        iid = next(iter(new_incidents))
        sig = ce._incident_signatures[iid]
        return {
            "incident_indexed": iid,
            "shape_signature":  _ser(sig),
        }

    # Default: propagate kind + canonical service name
    canonical = ce.memory.resolve(event.get("service") or "")
    return {"event_kind": kind, "service": canonical}


# ── REST endpoints ─────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/scenarios")
async def list_scenarios():
    return [
        {"name": s.name, "description": s.description}
        for s in _SCENARIOS.values()
    ]


@app.post("/reset")
async def reset():
    _reset()
    return {"status": "reset", "engine": "fresh"}


@app.get("/state")
async def state():
    return _read_state()


# ── WebSocket streaming endpoint ───────────────────────────────────────────────

@app.websocket("/stream/{scenario_name}")
async def stream_scenario(
    websocket:     WebSocket,
    scenario_name: str,
    speed:         str = "normal",
):
    await websocket.accept()

    if scenario_name not in _SCENARIOS:
        await websocket.send_text(json.dumps({
            "type":    "error",
            "message": f"Unknown scenario '{scenario_name}'. "
                       f"Available: {list(_SCENARIOS.keys())}",
        }))
        await websocket.close()
        return

    # Always start from a clean engine for each stream session.
    _reset()
    eng      = _get_engine()
    scenario = _SCENARIOS[scenario_name]
    delay    = _SPEED_DELAY.get(speed, 0.30)

    try:
        # ── Phase 1: stream events one by one ─────────────────────────────────
        for event in scenario.events:
            ce = eng._engine
            edges_before = set(ce.topology._g.edges())
            inc_before   = set(ce._incident_signatures.keys())

            eng.ingest([event])

            edges_after = set(ce.topology._g.edges())
            inc_after   = set(ce._incident_signatures.keys())

            delta = _state_delta(event, eng, edges_before, edges_after, inc_before, inc_after)

            await websocket.send_text(json.dumps({
                "type":        "event_ingested",
                "event":       event,
                "state_delta": delta,
            }, default=str))

            await asyncio.sleep(delay)

        # ── Phase 2: reconstruct context for each test signal ─────────────────
        for signal in scenario.test_signals:
            ctx = eng.reconstruct_context(signal, mode="fast")

            # Embed stored shape signatures into each similar-incident entry so
            # the frontend can render the tuple visualization without a second
            # request.  We access _engine internals read-only; no engine files
            # are modified.
            _ce = eng._engine
            augmented_incidents = [
                {
                    **inc,
                    "shape_signature": _ser(
                        list(_ce._incident_signatures[inc["past_incident_id"]])
                    ) if inc["past_incident_id"] in _ce._incident_signatures else [],
                }
                for inc in ctx["similar_past_incidents"]
            ]
            augmented_ctx = {**ctx, "similar_past_incidents": augmented_incidents}

            await websocket.send_text(json.dumps({
                "type":    "incident_resolved",
                "signal":  signal,
                "context": _ser(augmented_ctx),
            }, default=str))

        # ── Done ──────────────────────────────────────────────────────────────
        await websocket.send_text(json.dumps({"type": "scenario_complete"}))

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            await websocket.send_text(json.dumps({
                "type":    "error",
                "message": str(exc),
            }))
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
