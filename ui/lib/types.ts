export type EventKind =
  | "deploy"
  | "log"
  | "metric"
  | "trace"
  | "topology"
  | "incident_signal"
  | "remediation";

export interface EngineEvent {
  id: string;
  kind: EventKind;
  ts: number;
  service?: string;
  [key: string]: any;
}

export interface StateDelta {
  renamed?: { from: string; to: string };
  edge_added?: [string, string];
  edge_inferred?: [string, string];
  incident_indexed?: string;
  shape_signature?: any[];
  event_kind?: string;
  service?: string;
}

export interface CausalLink {
  cause_id: string;
  effect_id: string;
  evidence: string;
  confidence: number;
}

export interface SimilarIncident {
  past_incident_id: string;
  similarity: number;
  rationale: string;
  shape_signature?: any[];
}

export interface Remediation {
  action: string;
  target: string;
  historical_outcome: string;
  confidence: number;
}

export interface Context {
  related_events: EngineEvent[];
  causal_chain: CausalLink[];
  similar_past_incidents: SimilarIncident[];
  suggested_remediations: Remediation[];
  confidence: number;
  explain: string;
}

export interface WsMessage {
  type: "event_ingested" | "incident_resolved" | "scenario_complete" | "error";
  event?: EngineEvent;
  state_delta?: StateDelta;
  signal?: EngineEvent;
  context?: Context;
  message?: string;
}

export interface ScenarioInfo {
  name: string;
  description: string;
}
