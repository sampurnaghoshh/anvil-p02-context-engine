"use client";

import React from "react";
import { motion, AnimatePresence } from "framer-motion";

interface Props {
  signature: any[] | undefined;
  incidentId: string;
  similarity: number;
}

const ROLE_COLORS: Record<string, string> = {
  anchor:    "text-red-400",
  upstream:  "text-amber-400",
  downstream:"text-blue-400",
  peer:      "text-emerald-400",
};

function TupleRow({ tuple, idx }: { tuple: any[]; idx: number }) {
  const [role, kind, delta, hash] = tuple;
  const roleColor = ROLE_COLORS[role] ?? "text-gray-400";

  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: idx * 0.05 }}
      className="flex items-center gap-2 font-mono text-[11px] py-0.5"
    >
      <span className={`w-20 truncate ${roleColor}`}>{role}</span>
      <span className="text-gray-300 w-20 truncate">{kind}</span>
      <span className="text-purple-300 w-8 text-center">{delta >= 0 ? `+${delta}` : delta}</span>
      <span className="text-gray-500 truncate">{hash ?? ""}</span>
    </motion.div>
  );
}

export default function ShapeSignature({ signature, incidentId, similarity }: Props) {
  if (!signature || signature.length === 0) {
    return (
      <div className="text-gray-500 text-xs p-3">No shape signature available.</div>
    );
  }

  const pct = Math.round(similarity * 100);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-gray-400 font-mono">{incidentId}</span>
        <span
          className={`text-sm font-bold font-mono ${
            similarity >= 0.95 ? "text-emerald-400" : similarity >= 0.7 ? "text-amber-400" : "text-red-400"
          }`}
        >
          {pct}% match
        </span>
      </div>

      {/* Progress bar */}
      <div className="h-1.5 rounded bg-[#1f1f1f] overflow-hidden mb-2">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.6, ease: "easeOut" }}
          className={`h-full rounded ${
            similarity >= 0.95 ? "bg-emerald-400" : similarity >= 0.7 ? "bg-amber-400" : "bg-red-400"
          }`}
        />
      </div>

      {/* Tuple header */}
      <div className="flex items-center gap-2 font-mono text-[10px] text-gray-600 pb-1 border-b border-[#1f1f1f]">
        <span className="w-20">role</span>
        <span className="w-20">kind</span>
        <span className="w-8 text-center">Δt</span>
        <span>hash</span>
      </div>

      <AnimatePresence>
        {signature.map((t, i) => (
          <TupleRow key={i} tuple={Array.isArray(t) ? t : [t]} idx={i} />
        ))}
      </AnimatePresence>
    </div>
  );
}
