import sys, json
sys.path.insert(0, ".")
from engine.core import ContextEngine

engine = ContextEngine()

events = [
    {"id": "e1", "kind": "deploy",  "ts": 900.0,  "service": "auth-svc",    "version": "v2.1.0"},
    {"id": "e2", "kind": "log",     "ts": 950.0,  "service": "billing-svc", "level": "ERROR",
     "message": "timeout calling auth-svc"},
    {"id": "e3", "kind": "incident_signal", "ts": 1000.0, "service": "billing-svc",
     "incident_id": "INC-1", "severity": "high", "description": "billing latency spike"},
]
engine.ingest(events)

# Confirm _incident_signatures populated
print("=== _incident_signatures ===")
for iid, sig in engine._incident_signatures.items():
    print(f"  {iid}: signature length={len(sig)}, sig={sig}")

signal = {"id": "q1", "kind": "incident_signal", "ts": 1000.0,
          "service": "billing-svc", "severity": "high"}
ctx = engine.reconstruct_context(signal, mode="fast")

print("\n=== related_events ===")
for e in ctx["related_events"]:
    print(f"  {e}")

print("\n=== causal_chain ===")
if ctx["causal_chain"]:
    for edge in ctx["causal_chain"]:
        print(f"  {edge}")
else:
    print("  [] (expected: no topology edges built yet — auth-svc and billing-svc are not linked in graph)")

print("\n=== similar_past_incidents ===")
if ctx["similar_past_incidents"]:
    for s in ctx["similar_past_incidents"]:
        print(f"  {s}")
else:
    print("  [] (expected: query window == INC-1 window but INC-1 shape has len=2 events,")
    print("       query shape encodes the SAME window, so this should actually self-match)")
    # Diagnose: check the query shape vs stored shape
    import engine.shape as sh
    from engine.normalizer import EventNormalizer
    from engine.memory import EventMemory
    norm = engine.normalizer
    mem  = engine.memory
    topo = engine.topology
    raw  = mem.events_in_window(1000.0, 600.0)
    raw_filtered = [e for e in raw if e.get("id") != "e3"]
    print(f"\n  Stored INC-1 sig  : {engine._incident_signatures.get('INC-1')}")
    ne = norm.normalize_window(raw_filtered, 1000.0, "billing-svc", mem, topo)
    q_sig = engine.shape_encoder.encode(ne, "__query__", 400.0, 1000.0).signature
    print(f"  Query sig (same w): {q_sig}")
    print(f"  Signatures match  : {engine._incident_signatures.get('INC-1') == q_sig}")
    print(f"  Query sig length  : {len(q_sig)} (< 3, so ShapeIndex.query returns [] by design)")

print("\n=== suggested_remediations ===")
print(f"  {ctx['suggested_remediations']}")

print(f"\n=== confidence ===")
print(f"  {ctx['confidence']}")

print(f"\n=== explain ===")
print(f"  {ctx['explain']}")

engine.close()
print("\nsmoke test complete")
