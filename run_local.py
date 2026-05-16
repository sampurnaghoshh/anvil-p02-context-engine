"""
run_local.py -- CLI harness for running scenarios against the submission adapter.

Usage:
    python run_local.py                     # run all scenarios, fast mode
    python run_local.py --scenario rename_stress
    python run_local.py --mode deep
    python run_local.py --verbose           # full Context dump per signal
    python run_local.py --json out.json     # machine-readable output
"""
from __future__ import annotations

import argparse
import json
import sys
import time

sys.path.insert(0, ".")

try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init()
    GREEN  = Fore.GREEN
    RED    = Fore.RED
    YELLOW = Fore.YELLOW
    RESET  = Style.RESET_ALL
except ImportError:
    GREEN = RED = YELLOW = RESET = ""

from adapters.myteam import Engine
from scenario import all_scenarios, Scenario

SIM_THRESHOLD    = 0.7
WARN_QUERY_FAST  = 2_000   # ms
WARN_QUERY_DEEP  = 6_000   # ms
WARN_INGEST_PER_EVENT = 1  # ms


# ── Helpers ────────────────────────────────────────────────────────────────────

def _tag(passed: bool) -> str:
    if passed:
        return f"{GREEN}[PASS]{RESET}"
    return f"{RED}[FAIL]{RESET}"


def _warn(msg: str) -> str:
    return f"{YELLOW}[WARN]{RESET} {msg}"


def _fmt_ms(ms: float) -> str:
    return f"{ms:.1f}"


def _run_scenario(s: Scenario, mode: str, verbose: bool) -> dict:
    """Ingest + query one scenario through the adapter.  Returns result dict."""
    engine = Engine()

    t0 = time.perf_counter()
    engine.ingest(s.events)
    ingest_ms = (time.perf_counter() - t0) * 1_000

    signal_results = []
    for sig in s.test_signals:
        t1 = time.perf_counter()
        ctx = engine.reconstruct_context(sig, mode=mode)
        query_ms = (time.perf_counter() - t1) * 1_000

        matches = sorted(
            ctx.get("similar_past_incidents", []),
            key=lambda m: -m["similarity"],
        )
        top_match   = matches[0]["past_incident_id"] if matches else "-"
        top_sim     = matches[0]["similarity"] if matches else 0.0
        expected  = s.expected_matches.get(sig["id"], [])
        match_ids = {m["past_incident_id"] for m in matches if m["similarity"] >= SIM_THRESHOLD}

        if not expected:
            # Negative test: NOTHING should exceed the similarity threshold.
            passed = len(match_ids) == 0
            wrong  = [
                (m["past_incident_id"], m["similarity"])
                for m in matches if m["similarity"] >= SIM_THRESHOLD
            ]
        else:
            # Positive test: all expected incidents must appear above threshold.
            passed = all(exp in match_ids for exp in expected)
            wrong  = []

        signal_results.append({
            "id":         sig["id"],
            "query_ms":   round(query_ms, 2),
            "top_match":  top_match,
            "similarity": top_sim,
            "expected":   expected,
            "passed":     passed,
            "wrong":      wrong,   # false-positives for negative tests
            "context":    ctx if verbose else None,
        })

    engine.close()
    return {
        "name":      s.name,
        "ingest_ms": round(ingest_ms, 2),
        "signals":   signal_results,
    }


def _print_table(rows: list[dict], mode: str) -> None:
    """Print an ASCII summary table, then a footer with aggregate stats."""
    # Column headers
    headers = ["Scenario", "Signal", "Expected", "Top-Match", "Similarity", "Latency(ms)", "Status"]
    col_data: list[list[str]] = []

    for row in rows:
        for sig in row["signals"]:
            col_data.append([
                row["name"],
                sig["id"],
                ", ".join(sig["expected"]) if sig["expected"] else "(none)",
                sig["top_match"] or "-",
                f"{sig['similarity']:.3f}",
                _fmt_ms(sig["query_ms"]),
                _tag(sig["passed"]),
            ])

    # Compute visible widths (strip ANSI escapes for measurement)
    def _vlen(s: str) -> int:
        import re
        return len(re.sub(r"\x1b\[[0-9;]*m", "", s))

    widths = [len(h) for h in headers]
    for row in col_data:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], _vlen(cell))

    sep = "+" + "+".join("-" * (w + 2) for w in widths) + "+"

    def _fmt_row(cells: list[str]) -> str:
        parts = []
        for cell, w in zip(cells, widths):
            pad = w - _vlen(cell)
            parts.append(f" {cell}{' ' * pad} ")
        return "|" + "|".join(parts) + "|"

    print(sep)
    print(_fmt_row(headers))
    print(sep)
    for row in col_data:
        print(_fmt_row(row))
    print(sep)


def _print_footer(results: list[dict], mode: str, warnings: list[str]) -> None:
    total  = sum(len(r["signals"]) for r in results)
    passed = sum(sig["passed"] for r in results for sig in r["signals"])
    failed = total - passed

    total_events = 0
    total_ingest_ms = 0.0
    for r in results:
        # count events by looking at the scenario (we don't re-fetch here, use ingest_ms)
        total_ingest_ms += r["ingest_ms"]

    status_str = (
        f"{GREEN}{passed} passed{RESET}, {RED}{failed} failed{RESET} ({total} total)"
        if failed == 0
        else f"{passed} passed, {RED}{failed} failed{RESET} ({total} total)"
    )
    print(f"\nSummary: {status_str}")
    print(f"Mode: {mode}")

    for w in warnings:
        print(_warn(w))


def _emit_verbose(results: list[dict]) -> None:
    for r in results:
        for sig in r["signals"]:
            if sig.get("context") is not None:
                print(f"\n--- Context: scenario={r['name']}  signal={sig['id']} ---")
                ctx = sig["context"]
                printable = {
                    k: v for k, v in ctx.items() if k != "related_events"
                }
                printable["related_events_count"] = len(ctx.get("related_events", []))
                print(json.dumps(printable, indent=2, default=str))
                # For negative tests, explicitly call out every candidate and its sim
                if not sig["expected"]:
                    all_matches = ctx.get("similar_past_incidents", [])
                    if all_matches:
                        print(f"  [adversarial] all candidates (threshold={SIM_THRESHOLD}):")
                        for m in sorted(all_matches, key=lambda x: -x["similarity"]):
                            label = "FAIL-FP" if m["similarity"] >= SIM_THRESHOLD else "ok"
                            print(f"    {label}  {m['past_incident_id']}  sim={m['similarity']:.4f}")
                    else:
                        print(f"  [adversarial] no candidates returned (perfect discrimination)")


def _collect_warnings(results: list[dict], mode: str) -> list[str]:
    warnings = []
    budget = WARN_QUERY_FAST if mode == "fast" else WARN_QUERY_DEEP
    for r in results:
        for sig in r["signals"]:
            if sig["query_ms"] > budget:
                warnings.append(
                    f"{r['name']}/{sig['id']}: query {sig['query_ms']:.0f}ms "
                    f"> {budget}ms {mode}-mode budget"
                )
        # ingest per-event warning requires event count — approximate from ingest_ms
        # (we can't easily get count here without passing the scenario; skip for now)
    return warnings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Anvil P-02 scenarios against the submission adapter."
    )
    parser.add_argument(
        "--scenario", "-s",
        help="Run only this scenario by name (e.g. rename_stress)",
    )
    parser.add_argument(
        "--mode", "-m",
        choices=["fast", "deep"],
        default="fast",
        help="Reconstruction mode (default: fast)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print full Context dict (minus related_events list) for each signal",
    )
    parser.add_argument(
        "--json", "-j",
        metavar="PATH",
        help="Write machine-readable results to PATH",
    )
    args = parser.parse_args()

    scenarios = all_scenarios()
    if args.scenario:
        scenarios = [s for s in scenarios if s.name == args.scenario]
        if not scenarios:
            print(f"[ERROR] Unknown scenario '{args.scenario}'. "
                  f"Available: {[s.name for s in all_scenarios()]}")
            return 1

    results = [_run_scenario(s, mode=args.mode, verbose=args.verbose) for s in scenarios]
    warnings = _collect_warnings(results, args.mode)

    _print_table(results, args.mode)

    # Ingest latency warning (per event)
    for r, s in zip(results, scenarios):
        n = len(s.events)
        if n > 0:
            per_event = r["ingest_ms"] / n
            if per_event > WARN_INGEST_PER_EVENT:
                warnings.append(
                    f"{r['name']}: ingest {per_event:.2f}ms/event > "
                    f"{WARN_INGEST_PER_EVENT}ms budget"
                )
        print(f"  {r['name']}  ingest: {r['ingest_ms']:.1f}ms "
              f"({n} events, {r['ingest_ms']/n:.2f}ms/event)")

    _print_footer(results, args.mode, warnings)

    if args.verbose:
        _emit_verbose(results)

    if args.json:
        out = {
            "scenarios": results,
            "summary": {
                "total":     sum(len(r["signals"]) for r in results),
                "passed":    sum(sig["passed"] for r in results for sig in r["signals"]),
                "failed":    sum(not sig["passed"] for r in results for sig in r["signals"]),
                "fast_mode": args.mode == "fast",
            },
        }
        # context is not JSON-serialisable as-is (TypedDict values are fine, but
        # ctx may contain non-serialisable objects if verbose=False ctx=None)
        def _clean(obj):
            if isinstance(obj, dict):
                return {k: _clean(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_clean(v) for v in obj]
            if isinstance(obj, tuple):
                return list(obj)
            return obj

        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(_clean(out), fh, indent=2)
        print(f"\nResults written to {args.json}")

    total  = sum(len(r["signals"]) for r in results)
    passed = sum(sig["passed"] for r in results for sig in r["signals"])
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
