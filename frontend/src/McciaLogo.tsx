export function McciaLogo({
  className = "",
  height = 28,
  inverted = false,
}: {
  className?: string;
  height?: number;
  inverted?: boolean;
}) {
  const blue = inverted ? "#38BDF8" : "#0B62AC";
  const green = inverted ? "#4ADE80" : "#229E45";
  const regColor = inverted ? "#94A3B8" : "#0B62AC";

  // Aspect ratio is approx 3.2 : 1 (320x100)
  return (
    <svg
      viewBox="0 0 320 100"
      height={height}
      className={className}
      style={{ verticalAlign: "middle", overflow: "visible", flexShrink: 0 }}
      aria-label="MCCIA Logo"
    >
      <g>
        {/* Letter 'm' in MCCIA bold geometric styling */}
        <path
          d="M 12 28 H 32 C 38 28 42 32 44 38 C 47 32 52 28 59 28 H 76 V 78 H 58 V 44 C 58 41 55 39 52 39 C 48 39 45 41 45 44 V 78 H 27 V 44 C 27 41 24 39 21 39 C 17 39 15 41 15 44 V 78 H -3 V 28 H 12 Z"
          transform="translate(14, 0)"
          fill={blue}
        />

        {/* Letter 'c' 1 */}
        <path
          d="M 142 28 H 116 C 102 28 94 38 94 53 C 94 68 102 78 116 78 H 142 V 64 H 118 C 114 64 112 60 112 53 C 112 46 114 42 118 42 H 142 V 28 Z"
          fill={blue}
        />

        {/* Letter 'c' 2 */}
        <path
          d="M 196 28 H 170 C 156 28 148 38 148 53 C 148 68 156 78 170 78 H 196 V 64 H 172 C 168 64 166 60 166 53 C 166 46 168 42 172 42 H 196 V 28 Z"
          fill={blue}
        />

        {/* Letter 'i' in Vibrant Green */}
        <path d="M 204 28 H 222 V 78 H 204 V 28 Z" fill={green} />

        {/* Letter 'a' in Vibrant Green */}
        <path
          d="M 264 28 H 234 C 228 28 224 33 224 40 V 66 C 224 73 228 78 234 78 H 276 L 282 62 H 264 V 66 C 264 67 262 68 260 68 H 242 C 240 68 238 67 238 65 V 57 H 276 V 40 C 276 33 272 28 264 28 Z M 260 46 H 238 V 39 C 238 38 240 37 242 37 H 260 C 262 37 264 38 264 39 V 46 Z"
          fill={green}
        />

        {/* Registered Trademark symbol ® */}
        <g transform="translate(286, 20)">
          <circle cx="7" cy="7" r="6" stroke={regColor} strokeWidth="1.2" fill="none" />
          <text
            x="7"
            y="9.8"
            fontSize="6.5"
            fontFamily="Arial, sans-serif"
            fontWeight="bold"
            fill={regColor}
            textAnchor="middle"
          >
            R
          </text>
        </g>
      </g>
    </svg>
  );
}

export function McciaMark({ size = 32 }: { size?: number }) {
  return (
    <span
      className="mccia-mark-badge"
      style={{
        width: size,
        height: size,
        borderRadius: size * 0.28,
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        background: "linear-gradient(135deg, #0B62AC 0%, #0A2540 100%)",
        boxShadow: "0 2px 8px rgba(11, 98, 172, 0.25)",
        flexShrink: 0,
        position: "relative",
        overflow: "hidden",
      }}
    >
      <span
        style={{
          fontFamily: "Arial, sans-serif",
          fontWeight: 900,
          fontSize: size * 0.52,
          color: "#FFFFFF",
          letterSpacing: "-0.5px",
          marginLeft: "-2px",
        }}
      >
        m
      </span>
      <span
        style={{
          width: size * 0.22,
          height: size * 0.22,
          background: "#229E45",
          borderRadius: "50%",
          position: "absolute",
          top: size * 0.18,
          right: size * 0.18,
          border: "1.5px solid #0A2540",
        }}
      />
    </span>
  );
}
