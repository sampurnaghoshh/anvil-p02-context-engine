"""
scenario_verify.py — Validates the winning thesis:
    rename-invariant behavioral shape matching surfaces past incidents
    even after service renames.

Run: python scenario_verify.py
"""
import sys
sys.path.insert(0, ".")

from engine.core import ContextEngine
from scenario import all_scenarios

PASS = "[PASS]"
FAIL = "[FAIL]"
SIM_THRESHOLD = 0.9


def run_scenario(s) -> bool:
    sep = "=" * 64
    print(f"\n{sep}")
    print(f"Scenario : {s.name}")
    print(f"Desc     : {s.description}")
    print(f"{sep}")

    engine = ContextEngine()
    engine.ingest(s.events)

    print(f"  Indexed incidents : {list(engine._incident_signatures.keys())}")
    for iid, sig in engine._incident_signatures.items():
        print(f"    {iid} sig len={len(sig)}  sig={sig}")

    all_pass = True
    for signal in s.test_signals:
        ctx = engine.reconstruct_context(signal, mode="fast")

        sims = {
            m["past_incident_id"]: m["similarity"]
            for m in ctx["similar_past_incidents"]
        }

        print(f"\n  Signal  : {signal['id']}  ts={signal['ts']}  svc={signal.get('service')}")
        print(f"  related_events     : {len(ctx['related_events'])} events")
        print(f"  confidence         : {ctx['confidence']}")
        print(f"  similar_incidents  : {sims}")
        print(f"  causal_chain       : {len(ctx['causal_chain'])} edges")
        remeds = [(r["action"], round(r["confidence"], 3)) for r in ctx["suggested_remediations"]]
        print(f"  remediations       : {remeds}")
        print(f"  explain            : {ctx['explain']}")

        expected = s.expected_matches.get(signal["id"], [])
        for exp_iid in expected:
            if exp_iid not in sims:
                print(f"  {FAIL} {exp_iid} NOT found in similar_past_incidents")
                all_pass = False
            elif sims[exp_iid] < SIM_THRESHOLD:
                print(
                    f"  {FAIL} {exp_iid} found but sim={sims[exp_iid]:.4f} < "
                    f"{SIM_THRESHOLD} (threshold)"
                )
                all_pass = False
            else:
                print(
                    f"  {PASS} {exp_iid} found  sim={sims[exp_iid]:.4f}  "
                    f"(>= {SIM_THRESHOLD})"
                )

    engine.close()
    return all_pass


if __name__ == "__main__":
    scenarios = all_scenarios()
    results = [run_scenario(s) for s in scenarios]

    sep = "=" * 64
    print(f"\n{sep}")
    if all(results):
        print("THESIS VALIDATED -- rename-invariant behavioral shape matching works!")
        print("INC-001 (payments-svc) surfaced after rename to payment-service.")
    else:
        print("THESIS FAILED -- see failures above.")
    print(sep)

    sys.exit(0 if all(results) else 1)
