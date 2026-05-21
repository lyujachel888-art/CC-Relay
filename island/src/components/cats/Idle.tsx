export default function CatIdle({ size = 38 }: { size?: number }) {
  return (
    <svg
      className="cat-svg p8"
      width={size}
      height={size * 0.74}
      viewBox="0 0 54 48"
      style={{ opacity: 0.65 }}
    >
      <g style={{ animation: "breathe 4s ease-in-out infinite", transformOrigin: "27px 34px" }}>
        <ellipse cx="27" cy="36" rx="20" ry="11" className="bd" />
        <ellipse cx="27" cy="35" rx="18" ry="9.5" className="bm" />
        <circle cx="37" cy="22" r="10" className="bm" />
        <polygon points="29,15 32,7 36,15" className="bm" />
        <polygon points="38,14 41,6 45,13" className="bm" />
        <polygon points="30,15 32,9 35,15" className="bl" />
        <polygon points="39,14 41,8 44,14" className="bl" />
        <path d="M32 22 Q34 24.5 36 22" stroke="#374151" strokeWidth="1.5" strokeLinecap="round" fill="none" />
        <path d="M37 22 Q39 24.5 41 22" stroke="#374151" strokeWidth="1.5" strokeLinecap="round" fill="none" />
      </g>
      <g style={{ animation: "tail-sway 2.4s ease-in-out infinite", transformOrigin: "8px 30px" }}>
        <path d="M8 36 Q3 30 7 24 Q11 18 9 30" className="gl" strokeWidth="3.5" strokeLinecap="round" fill="none" />
      </g>
      <text x="5" y="16" fontSize="9" className="gf" fontFamily="sans-serif" fontWeight="bold"
        style={{ animation: "zzz 2.5s ease-in infinite" }}>z</text>
    </svg>
  );
}
