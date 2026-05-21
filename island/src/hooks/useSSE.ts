import { useEffect } from "react";
import { useSessions } from "../store/sessions";
import type { RawEvent } from "../lib/event-mapper";

const BRIDGE_URL = "http://127.0.0.1:8787/events";

export function useSSE() {
  const ingest = useSessions((s) => s.ingest);
  useEffect(() => {
    const src = new EventSource(BRIDGE_URL);
    src.onmessage = (msg) => {
      try {
        const event = JSON.parse(msg.data) as RawEvent;
        ingest(event);
      } catch (e) {
        console.warn("bad SSE payload", e);
      }
    };
    src.onerror = () => {
      // EventSource auto-reconnects after a delay; just log
      console.warn("SSE error; will auto-reconnect");
    };
    return () => src.close();
  }, [ingest]);
}
