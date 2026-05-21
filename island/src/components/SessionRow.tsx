import { invoke } from "@tauri-apps/api/core";
import FocusCat from "./FocusCat";
import HistoryTrail from "./HistoryTrail";
import TimeTag from "./TimeTag";
import { COLOR_MAIN } from "../lib/colors";
import { useSessions, type SessionState } from "../store/sessions";

interface Props { session: SessionState; }

export default function SessionRow({ session }: Props) {
  const toggleRecap = useSessions((s) => s.toggleRecap);
  const isError = session.state === "error";

  const onClick = async () => {
    try { await invoke("focus_terminal", { project: session.project }); }
    catch (e) { console.warn("focus_terminal failed", e); }
  };
  const onRightClick = (e: React.MouseEvent) => {
    e.preventDefault();
    toggleRecap(session.project);
  };

  return (
    <div
      className={`hud-row ${isError ? "err-row" : ""}`}
      onClick={onClick}
      onContextMenu={onRightClick}
    >
      <div className="row-left">
        <div
          className="dot"
          style={{
            background: COLOR_MAIN[session.color],
            boxShadow: `0 0 5px ${COLOR_MAIN[session.color]}`,
            animation: session.state === "working" || isError ? "dot-pulse 1.6s ease-in-out infinite" : "none",
          }}
        />
        <span
          className="tag"
          style={{
            background: `${COLOR_MAIN[session.color]}2E`,
            color: COLOR_MAIN[session.color],
            border: `1px solid ${COLOR_MAIN[session.color]}4D`,
          }}
        >{session.project}</span>
      </div>
      <div className="focus-area">
        <div className="focus-cat"><FocusCat state={session.state} priority={session.color} /></div>
      </div>
      <HistoryTrail history={session.history} />
      <TimeTag ts={session.lastEventAt} isError={isError} />
    </div>
  );
}
