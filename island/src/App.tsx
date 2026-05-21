import { useRef } from "react";
import "./App.css";
import { useDrag } from "./hooks/useDrag";
import { useSSE } from "./hooks/useSSE";
import { useSessions } from "./store/sessions";
import SessionRow from "./components/SessionRow";

export default function App() {
  const hudRef = useRef<HTMLDivElement>(null);
  useDrag(hudRef);
  useSSE();

  const sessions = useSessions((s) => Array.from(s.map.values()));

  return (
    <div className="hud" ref={hudRef}>
      {sessions.length === 0 ? (
        <div className="hud-placeholder">waiting for events…</div>
      ) : (
        sessions.map((s, i) => (
          <div key={s.project}>
            <SessionRow session={s} />
            {i < sessions.length - 1 && <div className="sep" />}
          </div>
        ))
      )}
    </div>
  );
}
