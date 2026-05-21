import { COLOR_MAIN, type Priority } from "../lib/colors";

export interface HistoryDot { color: Priority; ts: number; }

interface Props { history: HistoryDot[]; }

const SIZE_BY_INDEX = [4, 5, 6, 7, 8]; // tiny → big, rightmost current
const OPACITY_BY_INDEX = [0.35, 0.55, 0.75, 0.9, 1.0];

export default function HistoryTrail({ history }: Props) {
  if (history.length === 0) {
    return (
      <div className="history-trail empty">
        <span style={{ color: "#1e293b", fontSize: 10, letterSpacing: 2 }}>─ ─ ─ ─ ─</span>
      </div>
    );
  }
  // pad left with placeholders if < 5
  const padded: (HistoryDot | null)[] = Array(Math.max(0, 5 - history.length)).fill(null).concat(history);
  return (
    <div className="history-trail" style={{ display: "flex", alignItems: "center", gap: 4 }}>
      {padded.map((d, i) =>
        d ? (
          <div
            key={i}
            style={{
              width: SIZE_BY_INDEX[i],
              height: SIZE_BY_INDEX[i],
              borderRadius: "50%",
              background: COLOR_MAIN[d.color],
              opacity: i === 4 ? OPACITY_BY_INDEX[4] : OPACITY_BY_INDEX[i],
              boxShadow: i === 4 ? `0 0 6px ${COLOR_MAIN[d.color]}` : "none",
              flexShrink: 0,
            }}
          />
        ) : (
          <div key={i} style={{ width: SIZE_BY_INDEX[i], height: SIZE_BY_INDEX[i] }} />
        )
      )}
    </div>
  );
}
