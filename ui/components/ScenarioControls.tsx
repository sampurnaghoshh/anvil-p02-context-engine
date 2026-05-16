"use client";

import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Play, Square, RotateCcw } from "lucide-react";
import { useEngineStore } from "@/lib/engineState";
import { useWebSocket } from "@/lib/useWebSocket";
import { ScenarioInfo } from "@/lib/types";

const SPEEDS = [
  { id: "fast",   label: "Fast",   ms: 50 },
  { id: "normal", label: "Normal", ms: 300 },
  { id: "slow",   label: "Slow",   ms: 800 },
];

export default function ScenarioControls() {
  const { scenario, speed, running, complete, setScenario, setSpeed, reset } = useEngineStore();
  const { connect, disconnect } = useWebSocket();

  const [scenarios, setScenarios] = useState<ScenarioInfo[]>([]);
  const [fetchError, setFetchError] = useState(false);

  useEffect(() => {
    fetch("http://localhost:8000/scenarios")
      .then((r) => r.json())
      .then(setScenarios)
      .catch(() => setFetchError(true));
  }, []);

  const handlePlay = () => {
    if (running) {
      disconnect();
    } else {
      connect();
    }
  };

  const handleReset = () => {
    disconnect();
    reset();
    fetch("http://localhost:8000/reset", { method: "POST" }).catch(() => {});
  };

  return (
    <div className="flex flex-col gap-5 p-4">
      {/* Status badge */}
      <div className="flex items-center gap-2">
        <motion.div
          animate={{ opacity: running ? [1, 0.3, 1] : 1 }}
          transition={{ repeat: running ? Infinity : 0, duration: 1.2 }}
          className={`w-2 h-2 rounded-full ${
            running ? "bg-emerald-400" : complete ? "bg-blue-400" : "bg-gray-600"
          }`}
        />
        <span className="text-[11px] font-mono text-gray-400 uppercase tracking-widest">
          {running ? "Streaming" : complete ? "Complete" : "Idle"}
        </span>
      </div>

      {/* Scenario picker */}
      <div>
        <label className="text-[10px] text-gray-500 uppercase tracking-widest block mb-2">
          Scenario
        </label>
        {fetchError ? (
          <p className="text-red-400 text-[10px]">Server offline</p>
        ) : (
          <select
            value={scenario}
            onChange={(e) => setScenario(e.target.value)}
            disabled={running}
            className="w-full bg-[#111] border border-[#1f1f1f] text-gray-200 text-xs rounded px-2 py-1.5 font-mono focus:outline-none focus:border-emerald-400 disabled:opacity-50"
          >
            {scenarios.map((s) => (
              <option key={s.name} value={s.name}>
                {s.name}
              </option>
            ))}
            {scenarios.length === 0 && (
              <option value="rename_stress">rename_stress</option>
            )}
          </select>
        )}
        {scenarios.find((s) => s.name === scenario) && (
          <p className="text-[10px] text-gray-600 mt-1 leading-relaxed">
            {scenarios.find((s) => s.name === scenario)?.description}
          </p>
        )}
      </div>

      {/* Speed picker */}
      <div>
        <label className="text-[10px] text-gray-500 uppercase tracking-widest block mb-2">
          Speed
        </label>
        <div className="flex gap-1">
          {SPEEDS.map((s) => (
            <button
              key={s.id}
              onClick={() => setSpeed(s.id)}
              disabled={running}
              className={`flex-1 py-1.5 text-[11px] rounded font-medium transition-colors disabled:opacity-50 ${
                speed === s.id
                  ? "bg-emerald-400 text-black"
                  : "bg-[#1a1a1a] text-gray-400 hover:bg-[#222] hover:text-gray-200"
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      {/* Controls */}
      <div className="flex gap-2">
        <button
          onClick={handlePlay}
          className={`flex-1 flex items-center justify-center gap-2 py-2 rounded text-sm font-semibold transition-colors ${
            running
              ? "bg-amber-400 text-black hover:bg-amber-300"
              : "bg-emerald-400 text-black hover:bg-emerald-300"
          }`}
        >
          {running ? <Square size={14} /> : <Play size={14} />}
          {running ? "Stop" : "Play"}
        </button>
        <button
          onClick={handleReset}
          className="px-3 py-2 rounded bg-[#1a1a1a] text-gray-400 hover:bg-[#222] hover:text-gray-200 transition-colors"
        >
          <RotateCcw size={14} />
        </button>
      </div>

      {/* Indexed incidents */}
      <IndexedIncidentsList />
    </div>
  );
}

function IndexedIncidentsList() {
  const indexed = useEngineStore((s) => s.indexedIncidents);
  const setActive = useEngineStore((s) => s.setActiveResolution);
  const resolutions = useEngineStore((s) => s.resolutions);
  const active = useEngineStore((s) => s.activeResolution);

  if (indexed.length === 0) return null;

  return (
    <div>
      <label className="text-[10px] text-gray-500 uppercase tracking-widest block mb-2">
        Indexed Incidents
      </label>
      <div className="flex flex-col gap-1">
        {indexed.map((iid) => {
          const res = resolutions.find((r) => r.signalId === iid || r.context.similar_past_incidents.some((m) => m.past_incident_id === iid));
          const isActive = active?.signalId === res?.signalId;
          return (
            <button
              key={iid}
              onClick={() => res && setActive(res)}
              className={`text-left px-2 py-1.5 rounded text-[11px] font-mono transition-colors ${
                isActive
                  ? "bg-amber-400/20 text-amber-400 border border-amber-400/40"
                  : "bg-[#111] text-gray-400 border border-[#1f1f1f] hover:border-gray-600"
              }`}
            >
              {iid}
            </button>
          );
        })}
      </div>
    </div>
  );
}
