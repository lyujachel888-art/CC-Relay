import { invoke } from "@tauri-apps/api/core";
import type { SessionState } from "../store/sessions";

interface Props { session: SessionState; }

export default function RecapPanel({ session }: Props) {
  if (!session.recapOpen || !session.recap) return null;
  return (
    <div style={{
      margin: "0 12px 4px 36px",
      background: "rgba(99,102,241,.06)",
      border: "1px solid rgba(99,102,241,.2)",
      borderRadius: 8,
      padding: "8px 12px",
      maxHeight: 200, overflowY: "auto",
    }}>
      <div style={{ fontSize: 9, color: "#475569", textTransform: "uppercase", letterSpacing: ".07em", marginBottom: 6 }}>
        Recap
      </div>
      <div style={{ fontSize: 11, color: "#94A3B8", lineHeight: 1.5, whiteSpace: "pre-wrap" }}>
        {session.recap}
      </div>
      <div
        onClick={() => invoke("focus_terminal", { project: session.project }).catch(() => {})}
        style={{
          marginTop: 6, paddingTop: 6,
          borderTop: "1px solid rgba(255,255,255,.05)",
          fontSize: 10, color: "#334155", cursor: "pointer",
        }}
      >⌖ focus {session.project} terminal</div>
    </div>
  );
}
