🔨 Anvil P-02: Persistent Context Engine

Shazam for production outages. Recognize the shape of an incident — even after services get renamed, refactored, or rewritten.


⚡ The Pitch
When your microservices catch fire at 3 AM, this engine remembers every past inferno — even if you've renamed half the services since then. It turns chaotic incident telemetry into rename-invariant behavioral fingerprints, so on-call engineers get "we've seen this exact shape before, here's what fixed it" instead of a wall of logs.

🧠 The Core Idea
Most incident-similarity systems match on identifiers (service names, log strings, metric labels). That breaks the moment your team refactors payments-svc → billing-api.
Anvil matches on shapes:

Each incident is encoded as an ordered sequence of tuples:
(structural_role, event_kind, time_delta_bucket, payload_hash)

Payload hashes are computed after stripping service aliases and volatile tokens (versions, IDs, raw numbers). Two incidents with completely different names still hash to the same signature if the underlying causal pattern matches.
Same melody, different singer. Instant match.

✨ Features

🎯 Shape-based incident retrieval — signatures over identities; pattern over noise
🔄 Rename-invariant — svc-03-r4 → svc-03-r5 doesn't shatter your history
⚡ Dual-mode reasoning — fast for sub-second pager response, deep for causal-chain analysis
🧩 Adapter-based architecture — plug into any benchmark, log pipeline, or live telemetry source
📊 Causal chain reconstruction — surface cause → effect edges, not just similar incidents
🖥️ Full stack — Python engine + REST API + TypeScript UI + demo harness + scalability tests
📈 Benchmark-validated — ships with FINAL_BENCHMARK_REPORT.json and reproducible self-checks


📁 Repository Structure
anvil-p02-context-engine/
├── engine/           # Core context engine (normalizer, shape index, retrieval)
├── adapters/         # Bench + custom adapters
├── api/              # REST API surface
├── ui/               # TypeScript frontend
├── demo/             # Runnable demo scenarios
├── adapter.py        # Base Adapter class
├── schema.py         # NormalizedEvent, Shape, MatchResult, Context
├── run_local.py      # Local entry point
├── scenario.py       # Scenario harness
├── scalability_test.py
├── smoke_test.py
└── FINAL_BENCHMARK_REPORT.json

🚀 Quickstart
1. Install
bashgit clone https://github.com/sampurnaghoshh/anvil-p02-context-engine.git
cd anvil-p02-context-engine
pip install -r requirements.txt
2. Smoke test
bashpython smoke_test.py
3. Run a local scenario
bashpython run_local.py
4. Adapter smoke test
bashpython adapter_smoke.py
5. Scalability test
bashpython scalability_test.py

🧪 Programmatic Usage
pythonfrom engine.core import ContextEngine

engine = ContextEngine()

# Ingest a stream of events (logs, metrics, topology changes, deploys, etc.)
engine.ingest(event_stream)

# Reconstruct the context around a fresh incident signal
context = engine.reconstruct_context(signal, mode="fast")

# context contains:
#   - similar_past_incidents : ranked by shape similarity
#   - causal_chain           : cause → effect edges within the window
#   - related_events         : raw evidence for the on-call engineer
fast mode: index lookup, returns in milliseconds. Use when the pager screams.
deep mode: walks causal edges and partial-shape matches. Use during retros and post-mortems.

🔬 How It Works (One-Paragraph Version)
Events flow into an EventMemory keyed by time. The EventNormalizer strips volatile tokens (service aliases, versions, IDs) and emits NormalizedEvents with stable payload hashes. A TopologyGraph tracks rename edges so structural role (target, upstream, unrelated) is computed relative to the incident anchor — invariant under renames. The ShapeIndex stores both full signatures and indexable sub-sequences, enabling exact-match retrieval (similarity = 1.0) and partial-match retrieval for novel-but-related incidents. Retrieval returns ranked past incidents, a reconstructed causal chain, and the underlying evidence.

🌍 Real-World Applications

SRE / On-call tooling — instant déjà-vu detection on PagerDuty, Opsgenie, Datadog
Post-mortem clustering — group recurring failure families hidden behind cosmetic renames
Auto-remediation — surface what worked the last 5 times this shape appeared
Onboarding — let new engineers inherit institutional memory, not just runbooks
Refactor-safe observability — your incident history survives the next big rename


📊 Benchmarks
See FINAL_BENCHMARK_REPORT.json for the full breakdown. The engine is evaluated against the Anvil P-02 benchmark harness on:

recall@5 — did the correct past incident make the top 5?
precision@5 — how clean is that top 5?
remediation_acc — did we surface the right fix?
latency p95 — under the pager budget?

Reproduce with:
bashpython self_check.py --adapter adapters.myteam:Engine

🛠️ Tech Stack
LayerTechEnginePython 3.10+Hashinghashlib (MD5, truncated — for stability, not security)UITypeScriptAPIPython (REST)Benchmark harnessAnvil P-02 bench

🤝 Contributing
This is a benchmark submission, but the engine is designed to be extended. The cleanest extension points:

Custom normalizers — add domain-specific volatile-token rules in engine/normalizer.py
New adapters — implement the Adapter base class in adapter.py
Retrieval strategies — extend ShapeIndex with alternative scoring

PRs and issues welcome.

📜 License
See repository for license details.

🎭 In One Line

Shazam doesn't care if you hum off-key in a noisy bar. Anvil doesn't care if you renamed half your services last sprint.