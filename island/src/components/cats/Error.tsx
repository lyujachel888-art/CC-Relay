export default function CatError({ size = 34 }: { size?: number }) {
  return (
    <svg
      className="cat-svg p1"
      width={size}
      height={size * 0.94}
      viewBox="0 0 52 48"
      style={{ animation: "shiver .4s ease-in-out infinite" }}
    >
      <path d="M10 42 Q18 22 26 20 Q34 22 42 42 Z" className="bm" />
      <path d="M10 42 Q24 32 42 42" className="bd" />
      <g style={{ animation: "fur-pulse .7s ease-in-out infinite" }}>
        <line x1="16" y1="22" x2="11" y2="12" className="gl" strokeWidth="2" strokeLinecap="round" />
        <line x1="20" y1="19" x2="17" y2="9"  className="gl" strokeWidth="2" strokeLinecap="round" />
        <line x1="26" y1="18" x2="26" y2="8"  className="gl" strokeWidth="2" strokeLinecap="round" />
        <line x1="32" y1="19" x2="35" y2="9"  className="gl" strokeWidth="2" strokeLinecap="round" />
        <line x1="36" y1="22" x2="41" y2="12" className="gl" strokeWidth="2" strokeLinecap="round" />
      </g>
      <circle cx="26" cy="30" r="10" className="bm" />
      <polygon points="18,24 20,17 24,24" className="bm" />
      <polygon points="28,23 31,16 35,23" className="bm" />
      <circle cx="22" cy="31" r="4.5" fill="white" />
      <circle cx="30" cy="31" r="4.5" fill="white" />
      <circle cx="22" cy="31" r="2.5" fill="#1F2937" />
      <circle cx="30" cy="31" r="2.5" fill="#1F2937" />
      <circle cx="22" cy="30" r="1" fill="white" />
      <circle cx="30" cy="30" r="1" fill="white" />
    </svg>
  );
}
