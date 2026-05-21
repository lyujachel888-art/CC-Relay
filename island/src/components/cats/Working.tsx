import type { Priority } from "../../lib/colors";

export default function CatWorking({ priority = "p5", size = 38 }: { priority?: Priority; size?: number }) {
  return (
    <svg className={`cat-svg ${priority}`} width={size} height={size * 0.74} viewBox="0 0 58 46">
      <g style={{ animation: "stroll 1.8s cubic-bezier(0.37,0,0.63,1) infinite", transformOrigin: "bottom" }}>
        <ellipse cx="30" cy="28" rx="16" ry="9" className="bm" transform="rotate(-12 30 28)" />
        <circle cx="43" cy="17" r="10" className="bm" />
        <polygon points="36,10 39,2 43,10" className="bm" />
        <polygon points="43,9 46,1 50,9" className="bm" />
        <polygon points="37,10 39,4 42,10" className="bl" />
        <polygon points="44,9 46,3 49,9" className="bl" />
        <circle cx="40" cy="18" r="3" fill="#1F2937" />
        <circle cx="47" cy="17" r="3" fill="#1F2937" />
        <circle cx="41" cy="17" r="1.2" fill="white" />
        <circle cx="48" cy="16" r="1.2" fill="white" />
        <g style={{ animation: "leg-fl .8s ease-in-out infinite", transformOrigin: "22px 28px" }}>
          <line x1="22" y1="28" x2="14" y2="40" className="gl" strokeWidth="4" strokeLinecap="round" />
        </g>
        <g style={{ animation: "leg-fr .8s ease-in-out infinite", transformOrigin: "36px 32px" }}>
          <line x1="36" y1="32" x2="44" y2="42" className="gl" strokeWidth="4" strokeLinecap="round" />
        </g>
        <path d="M15 26 Q5 18 9 8" className="gl" strokeWidth="3.5" strokeLinecap="round" fill="none" />
      </g>
    </svg>
  );
}
