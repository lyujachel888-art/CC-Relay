import type { Priority } from "../../lib/colors";

export default function CatDone({ priority = "p4", size = 36 }: { priority?: Priority; size?: number }) {
  return (
    <svg className={`cat-svg ${priority}`} width={size} height={size * 0.89} viewBox="0 0 52 54">
      <g style={{ animation: "breathe 3.5s ease-in-out infinite", transformOrigin: "26px 40px" }}>
        <ellipse cx="26" cy="44" rx="12" ry="7" className="bd" />
        <ellipse cx="26" cy="41" rx="11" ry="11" className="bm" />
        <circle cx="26" cy="20" r="13" className="bm" />
        <polygon points="14,12 17,4 21,12" className="bm" />
        <polygon points="31,11 35,3 38,11" className="bm" />
        <polygon points="15,12 17,6 20,12" className="bl" />
        <polygon points="32,11 35,5 37,11" className="bl" />
        <path d="M19 22 Q21 19 23 22" stroke="#065F46" strokeWidth="2" strokeLinecap="round" fill="none" />
        <path d="M29 22 Q31 19 33 22" stroke="#065F46" strokeWidth="2" strokeLinecap="round" fill="none" />
      </g>
      <g style={{ animation: "wave-l 1.5s ease-in-out infinite", transformOrigin: "14px 36px" }}>
        <line x1="14" y1="36" x2="5" y2="24" className="gl" strokeWidth="4.5" strokeLinecap="round" />
      </g>
      <g style={{ animation: "wave-r 1.5s ease-in-out infinite", transformOrigin: "38px 36px" }}>
        <line x1="38" y1="36" x2="47" y2="24" className="gl" strokeWidth="4.5" strokeLinecap="round" />
      </g>
    </svg>
  );
}
