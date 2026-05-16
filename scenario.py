from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Scenario:
    name: str
    description: str
    events: list[dict]
    test_signals: list[dict]
    # signal_id -> list of incident_ids that MUST appear in similar_past_incidents
    expected_matches: dict[str, list[str]]


def _ev(id_: str, kind: str, ts: float, **kwargs: Any) -> dict:
    return {"id": id_, "kind": kind, "ts": ts, **kwargs}


def rename_stress_scenario() -> Scenario:
    """
    5-act rename stress test — the winning thesis proof.

    Topology:  checkout-api --> payments-svc --> db-cluster

    Act 1 (t=10-52):    Establish topology via explicit edges + trace spans.
    Act 2 (t=200-380):  Routine ops — safely OUTSIDE INC-001 window [460, 1060].
    Act 3 (t=1000-1100): INC-001 fires on payments-svc + remediation recorded.
    Act 4 (t=1400-1440): Rename payments-svc -> payment-service + re-traces.
                          All at t < 1460, so OUTSIDE INC-002 window [1460, 2060].
    Act 5 (t=2000-2060): INC-002 fires on payment-service (structurally identical).

    Rename-invariance proof:
      - deploy hash: md5("deploy|deploy")[:12]            — no version
      - metric hash: md5("metric|latency_p99|CRITICAL")   — threshold bracket, not raw value
      - anchor log:  _scrub replaces svc name -> _SVC_    — identical pre/post rename
      - upstream log: generic text, no svc name in msg    — identical pre/post rename
      - topology roles: BFS on renamed graph gives "upstream" for checkout-api in both cases

    Test signal ts=2059 (1s before INC-002 incident_signal at ts=2060), so the
    incident_signal is NOT in the query window [1459, 2059].
    Query sig == INC-001 stored sig == INC-002 stored sig -> sim=1.0.
    """
    events = [
        # ── Act 1: Establish topology ─────────────────────────────────────────
        # Explicit directed edges
        _ev("a1-e01", "topology", 10.0,
            change="add_edge", edge_source="checkout-api", edge_target="payments-svc"),
        _ev("a1-e02", "topology", 12.0,
            change="add_edge", edge_source="payments-svc", edge_target="db-cluster"),
        # Traces reinforce topology: checkout-api -> payments-svc -> db-cluster
        _ev("a1-e03", "trace", 20.0,
            service="checkout-api", span_id="sp01", status="ok", duration_ms=45.0),
        _ev("a1-e04", "trace", 21.0,
            service="payments-svc", span_id="sp02", parent_span_id="sp01",
            status="ok", duration_ms=30.0),
        _ev("a1-e05", "trace", 22.0,
            service="db-cluster", span_id="sp03", parent_span_id="sp02",
            status="ok", duration_ms=8.0),
        _ev("a1-e06", "trace", 50.0,
            service="checkout-api", span_id="sp04", status="ok", duration_ms=52.0),
        _ev("a1-e07", "trace", 51.0,
            service="payments-svc", span_id="sp05", parent_span_id="sp04",
            status="ok", duration_ms=28.0),
        _ev("a1-e08", "trace", 52.0,
            service="db-cluster", span_id="sp06", parent_span_id="sp05",
            status="ok", duration_ms=7.0),

        # ── Act 2: Routine ops — OUTSIDE INC-001 window [460, 1060] ──────────
        _ev("a2-e09", "log", 200.0,
            service="checkout-api", level="INFO",
            message="request processed successfully"),
        _ev("a2-e10", "log", 220.0,
            service="payments-svc", level="INFO",
            message="transaction completed"),
        _ev("a2-e11", "metric", 250.0,
            service="payments-svc",
            metric_name="latency_p99", value=120.0, threshold=200.0),
        _ev("a2-e12", "deploy", 300.0,
            service="checkout-api", version="v1.2.0"),
        _ev("a2-e13", "log", 350.0,
            service="payments-svc", level="INFO",
            message="health check passed"),
        _ev("a2-e14", "metric", 380.0,
            service="payments-svc",
            metric_name="latency_p99", value=90.0, threshold=200.0),

        # ── Act 3: INC-001 on payments-svc ───────────────────────────────────
        # INC-001 window = [460, 1060]; ONLY these 4 events fall inside.
        # Signature element 1: ("target","deploy",-2,md5("deploy|deploy")[:12])
        _ev("a3-e15", "deploy", 1000.0,
            service="payments-svc", version="v2.1.0"),
        # Signature element 2: ("target","metric",-2,md5("metric|latency_p99|CRITICAL")[:12])
        #   ratio = 650/200 = 3.25 > 2.0 -> "CRITICAL"
        _ev("a3-e16", "metric", 1005.0,
            service="payments-svc",
            metric_name="latency_p99", value=650.0, threshold=200.0),
        # Signature element 3: ("target","log",-1,md5("log|ERROR|_SVC_ processing timeout")[:12])
        #   _scrub replaces "payments-svc" -> "_SVC_"
        _ev("a3-e17", "log", 1040.0,
            service="payments-svc", level="ERROR",
            message="payments-svc processing timeout"),
        # Signature element 4: ("upstream","log",-1,md5("log|ERROR|upstream payment processor unavailable")[:12])
        #   "checkout-api" not in message -> _scrub changes nothing; hash identical pre/post rename
        _ev("a3-e18", "log", 1045.0,
            service="checkout-api", level="ERROR",
            message="upstream payment processor unavailable"),
        # Anchor incident — excluded from its own indexed signature (own_id filter)
        _ev("a3-e19", "incident_signal", 1060.0,
            service="payments-svc",
            incident_id="INC-001", severity="high",
            description="payments-svc latency critical"),
        # Remediation — linked to INC-001 signature for future suggestions
        _ev("a3-e20", "remediation", 1100.0,
            service="payments-svc",
            incident_id="INC-001", action="rollback", outcome="success"),

        # ── Act 4: Rename drift — all events OUTSIDE INC-002 window [1460, 2060] ──
        # Rename at t=1400 < 1460: topology node "payments-svc" -> "payment-service"
        _ev("a4-e21", "topology", 1400.0,
            change="rename", old_name="payments-svc", new_name="payment-service"),
        # New traces confirm checkout-api -> payment-service topology post-rename
        _ev("a4-e22", "trace", 1420.0,
            service="checkout-api", span_id="sp07", status="ok", duration_ms=48.0),
        _ev("a4-e23", "trace", 1421.0,
            service="payment-service", span_id="sp08", parent_span_id="sp07",
            status="ok", duration_ms=31.0),
        _ev("a4-e24", "log", 1440.0,
            service="payment-service", level="INFO",
            message="payment-service health check ok"),

        # ── Act 5: INC-002 on payment-service (post-rename) ──────────────────
        # INC-002 window = [1460, 2060]; ONLY these 4 events fall inside.
        # Structurally identical to INC-001's 4 events after rename-invariant encoding.
        # Signature element 1: ("target","deploy",-2,md5("deploy|deploy")[:12])
        _ev("a5-e25", "deploy", 2000.0,
            service="payment-service", version="v2.2.0"),
        # Signature element 2: ("target","metric",-2,md5("metric|latency_p99|CRITICAL")[:12])
        #   ratio = 720/200 = 3.6 > 2.0 -> "CRITICAL"
        _ev("a5-e26", "metric", 2005.0,
            service="payment-service",
            metric_name="latency_p99", value=720.0, threshold=200.0),
        # Signature element 3: ("target","log",-1,md5("log|ERROR|_SVC_ processing timeout")[:12])
        #   _scrub replaces "payment-service" -> "_SVC_"
        _ev("a5-e27", "log", 2040.0,
            service="payment-service", level="ERROR",
            message="payment-service processing timeout"),
        # Signature element 4: ("upstream","log",-1,md5("log|ERROR|upstream payment processor unavailable")[:12])
        #   Same message, same checkout-api canonical -> same hash
        _ev("a5-e28", "log", 2045.0,
            service="checkout-api", level="ERROR",
            message="upstream payment processor unavailable"),
        # INC-002 anchor — indexed with 4-element sig identical to INC-001's sig
        _ev("a5-e29", "incident_signal", 2060.0,
            service="payment-service",
            incident_id="INC-002", severity="high",
            description="payment-service latency critical"),
    ]

    # Query at ts=2059 (1s before a5-e29) -> window [1459, 2059] contains
    # exactly {a5-e25, a5-e26, a5-e27, a5-e28} — identical shape to INC-001.
    test_signals = [
        {
            "id": "q-rename-stress",
            "kind": "incident_signal",
            "ts": 2059.0,
            "service": "payment-service",
            "severity": "high",
        }
    ]

    expected_matches = {
        "q-rename-stress": ["INC-001"],
    }

    return Scenario(
        name="rename_stress",
        description=(
            "payments-svc renamed to payment-service between INC-001 and INC-002. "
            "Structurally identical behavioral shapes — rename-invariant encoding "
            "must surface INC-001 with similarity=1.0 despite the rename."
        ),
        events=events,
        test_signals=test_signals,
        expected_matches=expected_matches,
    )


def small_smoke_scenario() -> Scenario:
    """
    Two structurally identical incidents on auth-svc — no rename.
    Sanity check that basic shape matching works before rename complexity.

    INC-S1 window [-400, 200] = {deploy@100, metric@120, log@180}  (3 events)
    INC-S2 window [400, 1000] = {deploy@900, metric@940, log@980}   (3 events)

    Window isolation:
      - INC-S1 remediation@250 < 400 -> NOT in INC-S2 window
      - INC-S2 incident@1000 > 999  -> NOT in query window

    Query ts=999 window [399, 999] = {deploy@900, metric@940, log@980} = INC-S1 sig = INC-S2 sig
    -> both INC-S1 and INC-S2 appear in results with sim=1.0.
    """
    events = [
        # ── INC-S1 ────────────────────────────────────────────────────────────
        # INC-S1 window [-400, 200]: exactly these 3 events.
        # Sig[0]: ("target","deploy",-2,md5("deploy|deploy")[:12])  delta=100-200=-100->bucket=-2
        _ev("s-e01", "deploy", 100.0,
            service="auth-svc", version="v3.0.0"),
        # Sig[1]: ("target","metric",-2,md5("metric|error_rate|CRITICAL")[:12])
        #   ratio = 95/5 = 19.0 > 2.0 -> "CRITICAL"
        _ev("s-e02", "metric", 120.0,
            service="auth-svc",
            metric_name="error_rate", value=95.0, threshold=5.0),
        # Sig[2]: ("target","log",-1,md5("log|ERROR|_SVC_ connection refused")[:12])
        #   delta=180-200=-20 -> bucket=-1; _scrub "auth-svc" -> "_SVC_"
        _ev("s-e03", "log", 180.0,
            service="auth-svc", level="ERROR",
            message="auth-svc connection refused"),
        # Anchor — excluded from INC-S1 indexed sig
        _ev("s-e04", "incident_signal", 200.0,
            service="auth-svc",
            incident_id="INC-S1", severity="high",
            description="auth-svc connection failures"),
        # Remediation at t=250 < 400 -> outside INC-S2 window
        _ev("s-e05", "remediation", 250.0,
            service="auth-svc",
            incident_id="INC-S1", action="restart", outcome="success"),

        # ── INC-S2 ────────────────────────────────────────────────────────────
        # INC-S2 window [400, 1000]: exactly these 3 events.
        # Sig[0]: ("target","deploy",-2,...) delta=900-1000=-100->bucket=-2
        _ev("s-e06", "deploy", 900.0,
            service="auth-svc", version="v3.1.0"),
        # Sig[1]: ("target","metric",-2,...) ratio=88/5=17.6>2.0 -> "CRITICAL"
        _ev("s-e07", "metric", 940.0,
            service="auth-svc",
            metric_name="error_rate", value=88.0, threshold=5.0),
        # Sig[2]: ("target","log",-1,...) delta=980-1000=-20->bucket=-1
        _ev("s-e08", "log", 980.0,
            service="auth-svc", level="ERROR",
            message="auth-svc connection refused"),
        # Anchor — excluded from INC-S2 indexed sig
        _ev("s-e09", "incident_signal", 1000.0,
            service="auth-svc",
            incident_id="INC-S2", severity="high",
            description="auth-svc connection failures"),
    ]

    # ts=999 -> window [399, 999] -> {s-e06, s-e07, s-e08}; INC-S2 signal@1000 NOT included
    test_signals = [
        {
            "id": "q-smoke",
            "kind": "incident_signal",
            "ts": 999.0,
            "service": "auth-svc",
            "severity": "high",
        }
    ]

    expected_matches = {
        "q-smoke": ["INC-S1"],
    }

    return Scenario(
        name="small_smoke",
        description=(
            "Two identical auth-svc incidents — no rename. "
            "INC-S1 must appear with sim=1.0 when querying the INC-S2 context."
        ),
        events=events,
        test_signals=test_signals,
        expected_matches=expected_matches,
    )


def adversarial_negative_scenario() -> Scenario:
    """
    Discrimination test: two incidents that look superficially alike (deploy ->
    metric -> log) but differ structurally.  The engine must NOT match them.

    INC-A on auth-svc (isolated, same-service causal chain):
        Topology:  frontend -> auth-svc
        Shape:     (target,deploy,-2,*) (target,metric,-2,err_rate/CRITICAL)
                   (target,log,-1,*auth_fail*)
        Role pattern: all events on the anchor service itself.

    INC-B query on storage-svc (distributed, cross-service causal chain):
        Topology:  cache-svc -> storage-svc -> db-cluster
        Causal:    deploy on UPSTREAM (cache-svc), metric on DOWNSTREAM (db-cluster),
                   log on TARGET (storage-svc)
        Role pattern: upstream / downstream / target — structurally unlike INC-A.

    Why they do NOT match:
      - Deploy role: INC-A "target", INC-B query "upstream"  -> different tuple
      - Metric kind: INC-A error_rate, INC-B iops            -> different payload hash
      - Log message: "authentication failure" vs "write quorum lost"  -> different hash
      - The only partial sub-match is the shared topology+trace setup prefix
        (unknown/topology + upstream/trace + target/trace), which produces a
        3-element hit out of a 6-element stored sig and 8-element query sig.
        Score = 3 / max(6, 8) = 0.375  -- well below the 0.7 match threshold.

    adv-e17 (INC-B incident_signal) is intentionally NOT ingested so that INC-B
    does not self-index and trivially match its own query at sim=1.0, which would
    make the negative test vacuously pass for the wrong reason.
    """
    events = [
        # ── Topology for INC-A (frontend -> auth-svc) ─────────────────────────
        _ev("adv-e01", "topology", 10.0,
            change="add_edge", edge_source="frontend", edge_target="auth-svc"),
        _ev("adv-e02", "trace", 20.0,
            service="frontend", span_id="adv-sp01", status="ok", duration_ms=10.0),
        _ev("adv-e03", "trace", 21.0,
            service="auth-svc", span_id="adv-sp02", parent_span_id="adv-sp01",
            status="ok", duration_ms=8.0),

        # ── INC-A: same-service deploy -> metric -> log on auth-svc ───────────
        # INC-A window [-400, 200] captures adv-e01 through adv-e06 (6 events).
        # Sig: (unknown,topo,-3,*) (upstream,trace,-3,*) (target,trace,-3,*)
        #      (target,deploy,-2,*) (target,metric,-2,error_rate/CRITICAL)
        #      (target,log,-1,*authentication failure*)
        _ev("adv-e04", "deploy", 100.0,
            service="auth-svc", version="v4.0.0"),
        _ev("adv-e05", "metric", 120.0,
            service="auth-svc",
            metric_name="error_rate", value=80.0, threshold=5.0),   # 80/5=16 -> CRITICAL
        _ev("adv-e06", "log", 180.0,
            service="auth-svc", level="ERROR",
            message="auth-svc authentication failure"),
        _ev("adv-e07", "incident_signal", 200.0,
            service="auth-svc",
            incident_id="INC-A", severity="high",
            description="auth failures"),
        _ev("adv-e08", "remediation", 250.0,
            service="auth-svc",
            incident_id="INC-A", action="restart", outcome="success"),

        # ── Topology for INC-B (cache-svc -> storage-svc -> db-cluster) ───────
        _ev("adv-e09", "topology", 500.0,
            change="add_edge", edge_source="cache-svc", edge_target="storage-svc"),
        _ev("adv-e10", "topology", 501.0,
            change="add_edge", edge_source="storage-svc", edge_target="db-cluster"),
        _ev("adv-e11", "trace", 510.0,
            service="cache-svc", span_id="adv-sp03", status="ok", duration_ms=15.0),
        _ev("adv-e12", "trace", 511.0,
            service="storage-svc", span_id="adv-sp04", parent_span_id="adv-sp03",
            status="ok", duration_ms=12.0),
        _ev("adv-e13", "trace", 512.0,
            service="db-cluster", span_id="adv-sp05", parent_span_id="adv-sp04",
            status="ok", duration_ms=4.0),

        # ── INC-B causal events (no incident_signal — see docstring) ──────────
        # Query window [499, 1099] captures adv-e09 through adv-e16 (8 events).
        # Roles at anchor storage-svc:
        #   cache-svc   -> upstream   (edge: cache-svc -> storage-svc)
        #   db-cluster  -> downstream (edge: storage-svc -> db-cluster)
        #   storage-svc -> target
        _ev("adv-e14", "deploy", 1000.0,
            service="cache-svc", version="v2.0.0"),        # UPSTREAM deploy
        _ev("adv-e15", "metric", 1020.0,
            service="db-cluster",                           # DOWNSTREAM metric
            metric_name="iops", value=12000.0, threshold=3000.0),  # 12000/3000=4 -> CRITICAL
        _ev("adv-e16", "log", 1080.0,
            service="storage-svc", level="ERROR",
            message="storage-svc write quorum lost"),       # TARGET log, different message
        # adv-e17 (incident_signal for INC-B) intentionally omitted — see docstring.
    ]

    # Query at ts=1099 (1s before where INC-B signal would fire).
    # Window [499, 1099] captures adv-e09 through adv-e16 (8 events).
    # Only INC-A is indexed; expected similarity 3/max(8,6) = 0.375 < 0.7 threshold.
    test_signals = [
        {
            "id": "q-adversarial",
            "kind": "incident_signal",
            "ts": 1099.0,
            "service": "storage-svc",
            "severity": "high",
        }
    ]

    # Empty expected_matches = negative test: NOTHING should match above SIM_THRESHOLD.
    expected_matches: dict[str, list[str]] = {}

    return Scenario(
        name="adversarial_negative",
        description=(
            "Discrimination test: INC-A (same-service auth-svc shape) must NOT "
            "match a structurally different storage-svc query "
            "(upstream-deploy + downstream-metric + target-log). "
            "Role-aware encoding must keep sim below 0.7."
        ),
        events=events,
        test_signals=test_signals,
        expected_matches=expected_matches,
    )


def all_scenarios() -> list[Scenario]:
    return [rename_stress_scenario(), small_smoke_scenario(), adversarial_negative_scenario()]
