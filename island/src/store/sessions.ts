import { create } from "zustand";
import { mapEvent, type RawEvent } from "../lib/event-mapper";
import type { CatState } from "../components/FocusCat";
import type { Priority } from "../lib/colors";
import type { HistoryDot } from "../components/HistoryTrail";

export interface SessionState {
  project: string;
  state: CatState;
  color: Priority;
  history: HistoryDot[];
  recap: string | null;
  recapOpen: boolean;
  lastEventAt: number;
}

interface Store {
  map: Map<string, SessionState>;
  ingest: (e: RawEvent) => void;
  toggleRecap: (project: string) => void;
  markIdle: (project: string) => void;
}

export const useSessions = create<Store>((set) => ({
  map: new Map(),

  ingest: (e) => set((s) => {
    if (!e.project) return s;
    const mapped = mapEvent(e);
    const prev: SessionState = s.map.get(e.project) ?? {
      project: e.project, state: "idle", color: "p8",
      history: [], recap: null, recapOpen: false, lastEventAt: Date.now(),
    };
    const history = [...prev.history, { color: mapped.color, ts: Date.now() }].slice(-5);
    const next: SessionState = {
      ...prev,
      state: mapped.state,
      color: mapped.color,
      history,
      recap: e.type === "assistant_reply" ? e.text : prev.recap,
      lastEventAt: Date.now(),
    };
    const m = new Map(s.map); m.set(e.project, next);
    return { map: m };
  }),

  toggleRecap: (project) => set((s) => {
    const sess = s.map.get(project); if (!sess) return s;
    const m = new Map(s.map);
    m.set(project, { ...sess, recapOpen: !sess.recapOpen });
    return { map: m };
  }),

  markIdle: (project) => set((s) => {
    const sess = s.map.get(project); if (!sess) return s;
    const m = new Map(s.map);
    m.set(project, { ...sess, state: "idle", color: "p8" });
    return { map: m };
  }),
}));
