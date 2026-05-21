import { useEffect, useRef } from "react";
import "./App.css";
import { useDrag } from "./hooks/useDrag";
import { useSSE } from "./hooks/useSSE";
import { useSessions } from "./store/sessions";
import SessionRow from "./components/SessionRow";
import RecapPanel from "./components/RecapPanel";

export default function App() {
  const hudRef = useRef<HTMLDivElement>(null);
  useDrag(hudRef);
  useSSE();

  useEffect(() => {
    const id = setInterval(() => {
      const { map, markIdle } = useSessions.getState();
      const now = Date.now();
      map.forEach((s, project) => {
        if (s.state !== "idle" && s.state !== "done" && now - s.lastEventAt > 30_000) {
          markIdle(project);
        }
      });
    }, 1000);
    return () => clearInterval(id);
  }, []);

  const sessions = useSessions((s) => Array.from(s.map.values()));

  return (
    <div className="hud" ref={hudRef}>
      {sessions.length === 0 ? (
        <div className="hud-placeholder">waiting for events…</div>
      ) : (
        sessions.map((s, i) => (
          <div key={s.project}>
            <SessionRow session={s} />
            <RecapPanel session={s} />
            {i < sessions.length - 1 && <div className="sep" />}
          </div>
        ))
      )}
    </div>
  );
}
