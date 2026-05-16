"use client";

import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useEngineStore } from "@/lib/engineState";
import ShapeSignature from "./ShapeSignature";

type Tab = "matches" | "causal" | "remediation" | "explain";

const TAB_LABELS: { id: Tab; label: string }[] = [
  { id: "matches",     label: "Similar Incidents" },
  { id: "causal",      label: "Causal Chain" },
  { id: "remediation", label: "Remediation" },
  { id: "explain",     label: "Explain" },
];

export default function IncidentContext() {
  const resolution = useEngineStore((s) => s.activeResolution);
  const [tab, setTab] = useState<Tab>("matches");

  if (!resolution) {
    return (
      <div className="h-full flex items-center justify-center">
        <p className="text-gray-600 text-sm font-mono">Awaiting incident signal…</p>
      </div>
    );
  }

  const ctx = resolution.context;
  const topMatch = ctx.similar_past_incidents[0];
  const topSim = topMatch?.similarity ?? 0;
  const isPerfect = topSim >= 0.999;

  return (
    <motion.div
      key={resolution.signalId}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex flex-col h-full"
    >
      {/* ── Hero stat: top match similarity ─────────────────────────── */}
      <div
        className="px-4 pt-4 pb-3 border-b"
        style={{ borderColor: "#1f1f1f" }}
      >
        <div className="flex items-start justify-between">
          {/* Signal + top-match similarity */}
          <div>
            <span className="text-[10px] text-gray-500 uppercase tracking-widest">Signal</span>
            <p className="text-sm font-mono text-amber-400 font-semibold">{resolution.signalId}</p>
          </div>

          {/* THE HERO NUMBER */}
          <div className="text-right">
            <span className="text-[10px] text-gray-500 uppercase tracking-widest">
              {isPerfect ? "RENAME-INVARIANT MATCH" : "TOP MATCH"}
            </span>
            <motion.p
              animate={isPerfect ? {
                textShadow: [
                  "0 0 0px #34d399",
                  "0 0 16px #34d399",
                  "0 0 4px #34d399",
                  "0 0 16px #34d399",
                  "0 0 0px #34d399",
                ],
              } : {}}
              transition={{ duration: 2.4, repeat: Infinity, ease: "easeInOut" }}
              className={`text-2xl font-bold font-mono leading-tight ${
                topSim >= 0.999
                  ? "text-emerald-400"
                  : topSim >= 0.7
                  ? "text-amber-400"
                  : "text-red-400"
              }`}
            >
              {isPerfect ? "100% MATCH" : `${Math.round(topSim * 100)}%`}
            </motion.p>
            {topMatch && (
              <p className="text-[10px] text-gray-500 font-mono">
                {topMatch.past_incident_id} · {topSim.toFixed(4)}
              </p>
            )}
          </div>
        </div>

        {/* Secondary: context confidence */}
        <p className="text-[10px] text-gray-600 mt-2">
          context confidence:{" "}
          <span className="text-gray-400">{Math.round(ctx.confidence * 100)}%</span>
        </p>
      </div>

      {/* ── Tabs ─────────────────────────────────────────────────────── */}
      <div className="flex border-b" style={{ borderColor: "#1f1f1f" }}>
        {TAB_LABELS.map(({ id, label }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`px-3 py-2 text-[11px] font-medium transition-colors ${
              tab === id
                ? "text-emerald-400 border-b-2 border-emerald-400"
                : "text-gray-500 hover:text-gray-300"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* ── Tab body ─────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto px-4 py-3">
        <AnimatePresence mode="wait">
          {tab === "matches" && (
            <motion.div
              key="matches"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex flex-col gap-4"
            >
              {ctx.similar_past_incidents.length === 0 ? (
                <p className="text-gray-500 text-xs">No similar past incidents found.</p>
              ) : (
                ctx.similar_past_incidents.map((inc) => (
                  <div
                    key={inc.past_incident_id}
                    className="rounded-lg border p-3"
                    style={{ background: "#0d0d0d", borderColor: "#1f1f1f" }}
                  >
                    <ShapeSignature
                      signature={inc.shape_signature}
                      incidentId={inc.past_incident_id}
                      similarity={inc.similarity}
                    />
                    <p className="text-[10px] text-gray-500 font-mono mt-2 leading-relaxed">
                      {inc.rationale}
                    </p>
                  </div>
                ))
              )}
            </motion.div>
          )}

          {tab === "causal" && (
            <motion.div
              key="causal"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex flex-col gap-2"
            >
              {ctx.causal_chain.length === 0 ? (
                <p className="text-gray-500 text-xs">No causal chain derived.</p>
              ) : (
                ctx.causal_chain.map((link, i) => (
                  <div key={i} className="flex items-start gap-3 py-2 border-b" style={{ borderColor: "#1a1a1a" }}>
                    <div className="flex flex-col items-center">
                      <div className="w-2 h-2 rounded-full bg-amber-400 mt-1" />
                      {i < ctx.causal_chain.length - 1 && (
                        <div className="w-px h-6 mt-1" style={{ background: "#1f1f1f" }} />
                      )}
                    </div>
                    <div>
                      <p className="text-xs font-mono text-gray-200">
                        <span className="text-amber-400">{link.cause_id}</span>
                        <span className="text-gray-500"> → </span>
                        <span className="text-red-400">{link.effect_id}</span>
                      </p>
                      <p className="text-[10px] text-gray-500 mt-0.5">{link.evidence}</p>
                      <p className="text-[10px] text-emerald-600 mt-0.5">
                        confidence: {Math.round(link.confidence * 100)}%
                      </p>
                    </div>
                  </div>
                ))
              )}
            </motion.div>
          )}

          {tab === "remediation" && (
            <motion.div
              key="remediation"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex flex-col gap-3"
            >
              {ctx.suggested_remediations.length === 0 ? (
                <p className="text-gray-500 text-xs">No remediations suggested.</p>
              ) : (
                ctx.suggested_remediations.map((rem, i) => (
                  <div key={i} className="rounded border p-3" style={{ background: "#0d0d0d", borderColor: "#1f1f1f" }}>
                    <p className="text-xs font-semibold text-cyan-400 font-mono">{rem.action}</p>
                    <p className="text-[10px] text-gray-400 mt-1">
                      Target: <span className="text-gray-200">{rem.target}</span>
                    </p>
                    <p className="text-[10px] text-gray-500 mt-1">{rem.historical_outcome}</p>
                    <p className="text-[10px] text-emerald-600 mt-1">
                      confidence: {Math.round(rem.confidence * 100)}%
                    </p>
                  </div>
                ))
              )}
            </motion.div>
          )}

          {tab === "explain" && (
            <motion.div
              key="explain"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
            >
              <p className="text-xs text-gray-300 font-mono leading-relaxed whitespace-pre-wrap">
                {ctx.explain}
              </p>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  );
}
