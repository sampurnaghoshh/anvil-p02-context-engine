"use client";

import dynamic from "next/dynamic";
import ScenarioControls from "@/components/ScenarioControls";
import EventTimeline from "@/components/EventTimeline";
import IncidentContext from "@/components/IncidentContext";

// ReactFlow must be client-only (no SSR)
const TopologyGraph = dynamic(() => import("@/components/TopologyGraph"), { ssr: false });

export default function Home() {
  return (
    <div className="flex h-screen overflow-hidden" style={{ background: "#0a0a0a" }}>
      {/* ── Left sidebar: controls ───────────────────────────────────── */}
      <aside
        className="flex flex-col w-56 shrink-0 border-r overflow-y-auto"
        style={{ background: "#111", borderColor: "#1f1f1f" }}
      >
        <div
          className="px-4 py-3 border-b"
          style={{ borderColor: "#1f1f1f" }}
        >
          <h1 className="text-xs font-bold text-emerald-400 uppercase tracking-widest">
            Anvil P-02
          </h1>
          <p className="text-[10px] text-gray-600 mt-0.5">Context Engine</p>
        </div>
        <ScenarioControls />
      </aside>

      {/* ── Center: topology + event feed ───────────────────────────── */}
      <main className="flex flex-col flex-1 min-w-0">
        {/* Topology graph */}
        <div className="flex-1 min-h-0 border-b" style={{ borderColor: "#1f1f1f" }}>
          <TopologyGraph />
        </div>

        {/* Event timeline */}
        <div
          className="h-48 border-t"
          style={{ background: "#0d0d0d", borderColor: "#1f1f1f" }}
        >
          <div
            className="px-3 py-1.5 border-b flex items-center gap-2"
            style={{ borderColor: "#1f1f1f" }}
          >
            <span className="text-[9px] text-gray-500 uppercase tracking-widest">Event Feed</span>
          </div>
          <div className="h-[calc(100%-28px)] overflow-hidden">
            <EventTimeline />
          </div>
        </div>
      </main>

      {/* ── Right panel: incident context ────────────────────────────── */}
      <aside
        className="flex flex-col w-80 shrink-0 border-l overflow-hidden"
        style={{ background: "#111", borderColor: "#1f1f1f" }}
      >
        <div
          className="px-4 py-3 border-b"
          style={{ borderColor: "#1f1f1f" }}
        >
          <h2 className="text-xs font-bold text-amber-400 uppercase tracking-widest">
            Incident Context
          </h2>
          <p className="text-[10px] text-gray-600 mt-0.5">Shape-based recall</p>
        </div>
        <div className="flex-1 overflow-hidden">
          <IncidentContext />
        </div>
      </aside>
    </div>
  );
}
