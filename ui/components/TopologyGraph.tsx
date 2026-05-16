"use client";

import React, { useEffect, useCallback } from "react";
import ReactFlow, {
  Background,
  Controls,
  Edge,
  Node,
  NodeTypes,
  useNodesState,
  useEdgesState,
  useReactFlow,
  MarkerType,
  ReactFlowProvider,
} from "reactflow";
import "reactflow/dist/style.css";
import { motion, AnimatePresence } from "framer-motion";
import { useEngineStore, ServiceNode as SvcNode, TopoEdge } from "@/lib/engineState";

// ── Custom node ─────────────────────────────────────────────────────────────

function ServiceNodeComp({ data }: { data: any }) {
  const isRenaming = !!data.renaming;
  const isPulsing = !!data.incident;

  return (
    <motion.div
      initial={{ scale: 0.6, opacity: 0 }}
      animate={{
        scale: 1,
        opacity: 1,
        boxShadow: isRenaming
          ? "0 0 0 3px #a855f7, 0 0 20px #a855f780"
          : isPulsing
          ? "0 0 0 2px #fbbf24, 0 0 12px #fbbf2480"
          : "0 0 0 1px #1f1f1f",
      }}
      transition={{ duration: 0.35 }}
      className="rounded-lg px-3 py-2 text-xs font-mono min-w-[120px] text-center"
      style={{
        background: "#111",
        border: isRenaming
          ? "1px solid #a855f7"
          : isPulsing
          ? "1px solid #fbbf24"
          : "1px solid #1f1f1f",
        color: isRenaming ? "#d8b4fe" : "#d1d5db",
      }}
    >
      {isRenaming ? (
        <AnimatePresence mode="wait">
          <motion.div key="rename-label">
            <motion.span
              initial={{ opacity: 1 }}
              animate={{ opacity: 0 }}
              transition={{ duration: 0.8 }}
              className="line-through text-purple-400 block text-[10px]"
            >
              {data.renaming.from}
            </motion.span>
            <motion.span
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.3, duration: 0.8 }}
              className="text-purple-200 font-semibold block"
            >
              {data.label}
            </motion.span>
          </motion.div>
        </AnimatePresence>
      ) : (
        <span>{data.label}</span>
      )}
    </motion.div>
  );
}

const nodeTypes: NodeTypes = { service: ServiceNodeComp };

// ── Converters ───────────────────────────────────────────────────────────────

function toRFNode(n: SvcNode, incidents: string[]): Node {
  const hasIncident = incidents.some((iid) =>
    n.label.includes(iid.split("-")[0])
  );
  return {
    id: n.id,
    type: "service",
    position: { x: n.x, y: n.y },
    data: {
      label: n.label,
      renaming:
        n.renaming && Date.now() - n.renaming.startedAt < 2500
          ? n.renaming
          : undefined,
      incident: hasIncident,
    },
  };
}

function toRFEdge(e: TopoEdge): Edge {
  return {
    id: e.id,
    source: e.source,
    target: e.target,
    animated: e.inferred,
    style: {
      stroke: e.inferred ? "#6b7280" : "#34d399",
      strokeWidth: 1.5,
    },
    markerEnd: {
      type: MarkerType.ArrowClosed,
      color: e.inferred ? "#6b7280" : "#34d399",
    },
  };
}

// ── FitView helper (must be inside ReactFlow's context) ──────────────────────

function FitViewOnChange({ nodeCount }: { nodeCount: number }) {
  const { fitView } = useReactFlow();
  useEffect(() => {
    if (nodeCount > 0) {
      fitView({ padding: 0.3, duration: 400 });
    }
  }, [nodeCount, fitView]);
  return null;
}

// ── Rename banner ────────────────────────────────────────────────────────────

function RenameBanner() {
  const lastRename = useEngineStore((s) => s.lastRename);
  const visible = !!lastRename && Date.now() - lastRename.at < 3000;

  return (
    <AnimatePresence>
      {visible && lastRename && (
        <motion.div
          key={`${lastRename.from}-${lastRename.to}`}
          initial={{ opacity: 0, y: -16 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -16 }}
          transition={{ duration: 0.3 }}
          className="absolute top-0 left-0 right-0 z-10 flex items-center justify-center gap-3 py-2 text-sm font-mono font-semibold"
          style={{
            background: "linear-gradient(90deg, #581c87 0%, #7c3aed 50%, #581c87 100%)",
            borderBottom: "1px solid #a855f7",
            color: "#e9d5ff",
          }}
        >
          <motion.span
            animate={{ opacity: [1, 0.5, 1] }}
            transition={{ duration: 1.2, repeat: Infinity }}
          >
            ⟳
          </motion.span>
          <span>SERVICE RENAME</span>
          <span className="text-purple-300">{lastRename.from}</span>
          <span className="text-purple-500">→</span>
          <span className="text-white font-bold">{lastRename.to}</span>
          <span className="text-purple-400 text-[10px] ml-2">rename-invariant encoding active</span>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

// ── Inner graph (needs ReactFlow context for useReactFlow) ───────────────────

function GraphInner() {
  const storeNodes = useEngineStore((s) => s.nodes);
  const storeEdges = useEngineStore((s) => s.edges);
  const indexedIncidents = useEngineStore((s) => s.indexedIncidents);

  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  useEffect(() => {
    setNodes(storeNodes.map((n) => toRFNode(n, indexedIncidents)));
    setEdges(storeEdges.map(toRFEdge));
  }, [storeNodes, storeEdges, indexedIncidents, setNodes, setEdges]);

  return (
    <>
      <FitViewOnChange nodeCount={nodes.length} />
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#1a1a1a" gap={24} />
        <Controls
          style={{ background: "#111", borderColor: "#1f1f1f" }}
          showInteractive={false}
        />
      </ReactFlow>
    </>
  );
}

// ── Public component ─────────────────────────────────────────────────────────

export default function TopologyGraph() {
  return (
    <div className="relative w-full h-full" style={{ background: "#0a0a0a" }}>
      <RenameBanner />
      <ReactFlowProvider>
        <GraphInner />
      </ReactFlowProvider>
    </div>
  );
}
