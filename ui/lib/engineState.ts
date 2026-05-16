"use client";

import { create } from "zustand";
import { EngineEvent, StateDelta, Context } from "./types";

export interface ServiceNode {
  id: string;
  label: string;
  x: number;
  y: number;
  renaming?: { from: string; to: string; startedAt: number };
}

export interface TopoEdge {
  id: string;
  source: string;
  target: string;
  inferred: boolean;
}

export interface IncidentResolution {
  signalId: string;
  context: Context;
  resolvedAt: number;
}

interface EngineStore {
  // Topology
  nodes: ServiceNode[];
  edges: TopoEdge[];

  // Events feed
  events: Array<{ event: EngineEvent; delta: StateDelta }>;

  // Incident state
  indexedIncidents: string[];
  incidentSignatures: Record<string, any[]>;
  resolutions: IncidentResolution[];
  activeResolution: IncidentResolution | null;

  // Rename banner
  lastRename: { from: string; to: string; at: number } | null;

  // Playback
  running: boolean;
  complete: boolean;
  scenario: string;
  speed: string;

  // Actions
  setScenario: (s: string) => void;
  setSpeed: (s: string) => void;
  applyDelta: (event: EngineEvent, delta: StateDelta) => void;
  applyResolution: (signalId: string, context: Context) => void;
  setRunning: (v: boolean) => void;
  setComplete: (v: boolean) => void;
  setActiveResolution: (r: IncidentResolution | null) => void;
  reset: () => void;
}

const LAYOUT_COLS = 4;
const LAYOUT_H_GAP = 200;
const LAYOUT_V_GAP = 140;
const LAYOUT_OFFSET_X = 60;
const LAYOUT_OFFSET_Y = 60;

function positionForIndex(idx: number): { x: number; y: number } {
  const col = idx % LAYOUT_COLS;
  const row = Math.floor(idx / LAYOUT_COLS);
  return {
    x: LAYOUT_OFFSET_X + col * LAYOUT_H_GAP,
    y: LAYOUT_OFFSET_Y + row * LAYOUT_V_GAP,
  };
}

export const useEngineStore = create<EngineStore>((set) => ({
  nodes: [],
  edges: [],
  events: [],
  indexedIncidents: [],
  incidentSignatures: {},
  resolutions: [],
  activeResolution: null,
  lastRename: null,
  running: false,
  complete: false,
  scenario: "rename_stress",
  speed: "fast",

  setScenario: (s) => set({ scenario: s }),
  setSpeed: (s) => set({ speed: s }),
  setRunning: (v) => set({ running: v }),
  setComplete: (v) => set({ complete: v }),
  setActiveResolution: (r) => set({ activeResolution: r }),

  applyDelta: (event, delta) => {
    set((state) => {
      const newEvents = [...state.events, { event, delta }].slice(-60);

      let nodes = [...state.nodes];
      let edges = [...state.edges];
      const indexedIncidents = [...state.indexedIncidents];
      const incidentSignatures = { ...state.incidentSignatures };
      let lastRename = state.lastRename;

      const ensureNode = (name: string) => {
        if (!name) return;
        if (!nodes.find((n) => n.id === name)) {
          const pos = positionForIndex(nodes.length);
          nodes.push({ id: name, label: name, ...pos });
          console.log("[topology] added node:", name, "at", pos);
        }
      };

      const ensureEdge = (src: string, dst: string, inferred: boolean) => {
        const eid = `${src}--${dst}`;
        if (!edges.find((e) => e.id === eid)) {
          edges.push({ id: eid, source: src, target: dst, inferred });
          console.log("[topology] added edge:", src, "→", dst, inferred ? "(inferred)" : "");
        }
      };

      if (delta.renamed) {
        const { from, to } = delta.renamed;
        lastRename = { from, to, at: Date.now() };
        console.log("[topology] RENAME:", from, "→", to);

        // Rename the node in-place; keep position
        let found = false;
        nodes = nodes.map((n) => {
          if (n.id === from) {
            found = true;
            return { ...n, id: to, label: to, renaming: { from, to, startedAt: Date.now() } };
          }
          return n;
        });
        // If the old node didn't exist yet, just add the new one with rename flag
        if (!found) {
          ensureNode(to);
          nodes = nodes.map((n) =>
            n.id === to ? { ...n, renaming: { from, to, startedAt: Date.now() } } : n
          );
        }
        // Update edges: any reference to `from` becomes `to`
        edges = edges.map((e) => {
          const src = e.source === from ? to : e.source;
          const dst = e.target === from ? to : e.target;
          return { ...e, id: `${src}--${dst}`, source: src, target: dst };
        });
      } else if (delta.edge_added) {
        const [src, dst] = delta.edge_added;
        ensureNode(src);
        ensureNode(dst);
        ensureEdge(src, dst, false);
      } else if (delta.edge_inferred) {
        const [src, dst] = delta.edge_inferred;
        ensureNode(src);
        ensureNode(dst);
        ensureEdge(src, dst, true);
        console.log("[topology] edge_inferred:", src, "→", dst);
      } else if (delta.incident_indexed) {
        const iid = delta.incident_indexed;
        if (!indexedIncidents.includes(iid)) {
          indexedIncidents.push(iid);
        }
        if (delta.shape_signature && delta.shape_signature.length > 0) {
          incidentSignatures[iid] = delta.shape_signature;
          console.log("[incident] stored signature for", iid, ":", delta.shape_signature.length, "tuples");
        }
        const svc = event.service || "";
        if (svc) ensureNode(svc);
      } else {
        const svc = delta.service || event.service || "";
        if (svc) ensureNode(svc);
      }

      return {
        events: newEvents,
        nodes,
        edges,
        indexedIncidents,
        incidentSignatures,
        lastRename,
      };
    });
  },

  applyResolution: (signalId, context) => {
    const resolution: IncidentResolution = {
      signalId,
      context,
      resolvedAt: Date.now(),
    };
    set((state) => ({
      resolutions: [...state.resolutions, resolution],
      activeResolution: resolution,
    }));
  },

  reset: () =>
    set({
      nodes: [],
      edges: [],
      events: [],
      indexedIncidents: [],
      incidentSignatures: {},
      resolutions: [],
      activeResolution: null,
      lastRename: null,
      running: false,
      complete: false,
    }),
}));
