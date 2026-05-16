import sys
sys.path.insert(0, ".")
from adapters.myteam import Engine

eng = Engine()
eng.ingest([
    {"id": "e1", "kind": "deploy", "ts": 100.0, "service": "svc-a", "version": "v1"},
    {"id": "e2", "kind": "incident_signal", "ts": 200.0, "service": "svc-a",
     "incident_id": "INC-X", "severity": "high"},
])
ctx = eng.reconstruct_context(
    {"id": "q1", "kind": "incident_signal", "ts": 200.0, "service": "svc-a"}
)
required = ["related_events", "causal_chain", "similar_past_incidents",
            "suggested_remediations", "confidence", "explain"]
assert all(k in ctx for k in required), f"Missing fields: {[k for k in required if k not in ctx]}"
print("adapter smoke test PASSED")
eng.close()
