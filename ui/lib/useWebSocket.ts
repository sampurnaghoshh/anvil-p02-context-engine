"use client";

import { useRef, useCallback } from "react";
import { useEngineStore } from "./engineState";
import { WsMessage } from "./types";

const WS_BASE = "ws://localhost:8000";

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const { applyDelta, applyResolution, setRunning, setComplete, reset, scenario, speed } =
    useEngineStore();

  const connect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
    }
    reset();
    setRunning(true);
    setComplete(false);

    const ws = new WebSocket(`${WS_BASE}/stream/${scenario}?speed=${speed}`);
    wsRef.current = ws;

    ws.onmessage = (ev) => {
      const msg: WsMessage = JSON.parse(ev.data);

      if (msg.type === "event_ingested" && msg.event && msg.state_delta) {
        applyDelta(msg.event, msg.state_delta);
      } else if (msg.type === "incident_resolved" && msg.signal && msg.context) {
        applyResolution(msg.signal.id, msg.context);
      } else if (msg.type === "scenario_complete") {
        setRunning(false);
        setComplete(true);
        ws.close();
      } else if (msg.type === "error") {
        console.error("WS error:", msg.message);
        setRunning(false);
      }
    };

    ws.onerror = () => {
      setRunning(false);
    };

    ws.onclose = () => {
      setRunning(false);
    };
  }, [scenario, speed, applyDelta, applyResolution, setRunning, setComplete, reset]);

  const disconnect = useCallback(() => {
    wsRef.current?.close();
    setRunning(false);
  }, [setRunning]);

  return { connect, disconnect };
}
