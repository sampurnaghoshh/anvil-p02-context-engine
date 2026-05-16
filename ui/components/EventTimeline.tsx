"use client";

import React, { useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useEngineStore } from "@/lib/engineState";
import { EventKind } from "@/lib/types";

const KIND_COLORS: Record<EventKind | string, string> = {
  deploy:           "bg-blue-500",
  log:              "bg-slate-400",
  metric:           "bg-amber-400",
  trace:            "bg-emerald-400",
  topology:         "bg-purple-400",
  incident_signal:  "bg-red-500",
  remediation:      "bg-cyan-400",
};

const KIND_LABEL: Record<EventKind | string, string> = {
  deploy:           "DEPLOY",
  log:              "LOG",
  metric:           "METRIC",
  trace:            "TRACE",
  topology:         "TOPO",
  incident_signal:  "INCIDENT",
  remediation:      "REMEDIATION",
};

export default function EventTimeline() {
  const events = useEngineStore((s) => s.events);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events.length]);

  return (
    <div className="flex flex-col gap-1 overflow-y-auto h-full px-3 py-2">
      <AnimatePresence initial={false}>
        {events.map(({ event, delta }, i) => {
          const color = KIND_COLORS[event.kind] ?? "bg-gray-500";
          const label = KIND_LABEL[event.kind] ?? event.kind.toUpperCase();
          const svc = delta.service || event.service || "";
          const rename = delta.renamed;
          const edgeAdded = delta.edge_added;
          const incIndexed = delta.incident_indexed;

          return (
            <motion.div
              key={`${event.id}-${i}`}
              initial={{ opacity: 0, x: -12 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="flex items-start gap-2 py-1 border-b border-[#1a1a1a] last:border-0"
            >
              <span
                className={`mt-0.5 shrink-0 text-[9px] font-bold px-1.5 py-0.5 rounded text-black ${color}`}
              >
                {label}
              </span>
              <div className="flex-1 min-w-0">
                <span className="text-xs font-mono text-gray-300 truncate block">
                  {rename
                    ? `${rename.from} → ${rename.to}`
                    : edgeAdded
                    ? `edge: ${edgeAdded[0]} → ${edgeAdded[1]}`
                    : incIndexed
                    ? `indexed: ${incIndexed}`
                    : svc || event.id}
                </span>
              </div>
              <span className="text-[9px] text-gray-600 font-mono shrink-0">
                {event.ts.toFixed(0)}
              </span>
            </motion.div>
          );
        })}
      </AnimatePresence>
      <div ref={endRef} />
    </div>
  );
}
