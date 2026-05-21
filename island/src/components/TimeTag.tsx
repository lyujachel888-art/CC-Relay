import { useEffect, useState } from "react";

function fmt(ts: number): string {
  const sec = (Date.now() - ts) / 1000;
  if (sec < 60)   return `${Math.floor(sec)}s`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m`;
  return `${Math.floor(sec / 3600)}h`;
}

interface Props { ts: number; isError?: boolean; }

export default function TimeTag({ ts, isError }: Props) {
  const [, force] = useState(0);
  useEffect(() => {
    const id = setInterval(() => force((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, []);
  return (
    <span
      className="time-tag"
      style={{
        fontSize: 9.5,
        color: isError ? "#FCA5A5" : "#475569",
        fontVariantNumeric: "tabular-nums",
        minWidth: 32,
        textAlign: "right",
        fontWeight: isError ? 700 : 400,
        flexShrink: 0,
      }}
    >{fmt(ts)}</span>
  );
}
