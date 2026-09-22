import type { CSSProperties } from "react";

interface BrandLogoProps {
  className?: string;
  size?: number;
  showText?: boolean;
  title?: string;
  subtitle?: string;
  showAiBadge?: boolean;
  theme?: "dark" | "light" | "auto";
  style?: CSSProperties;
  variant?: "brand" | "compact" | "icon-only" | "mccia";
}

/**
 * High-tech precision vector icon for PromiseFlow / ProductionSaathi.
 * Features interconnected manufacturing flow nodes, pulse arcs, and glowing gradients.
 */
export function BrandIcon({ size = 32, className = "" }: { size?: number; className?: string }) {
  const uid = "pf-grad-" + Math.round(size);
  return (
    <svg
      className={`brand-icon-svg ${className}`.trim()}
      width={size}
      height={size}
      viewBox="0 0 48 48"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      style={{ flexShrink: 0, display: "inline-block", verticalAlign: "middle" }}
    >
      <defs>
        {/* Main Brand Gradient */}
        <linearGradient id={`${uid}-primary`} x1="4" y1="4" x2="44" y2="44" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#38BDF8" />
          <stop offset="50%" stopColor="#2563EB" />
          <stop offset="100%" stopColor="#10B981" />
        </linearGradient>

        {/* Accent Glow Gradient */}
        <linearGradient id={`${uid}-accent`} x1="12" y1="12" x2="36" y2="36" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#67E8F9" />
          <stop offset="100%" stopColor="#34D399" />
        </linearGradient>

        {/* Background Badge Gradient */}
        <linearGradient id={`${uid}-bg`} x1="0" y1="0" x2="48" y2="48" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#0E2A47" />
          <stop offset="100%" stopColor="#061826" />
        </linearGradient>

        {/* Subtle Glow Filter */}
        <filter id={`${uid}-glow`} x="-20%" y="-20%" width="140%" height="140%">
          <feDropShadow dx="0" dy="2" stdDeviation="3" floodColor="#38BDF8" floodOpacity="0.35" />
        </filter>
      </defs>

      {/* Rounded Squircle Container */}
      <rect
        x="2"
        y="2"
        width="44"
        height="44"
        rx="12"
        fill={`url(#${uid}-bg)`}
        stroke={`url(#${uid}-primary)`}
        strokeWidth="1.5"
        strokeOpacity="0.8"
      />

      {/* Inner ambient glow */}
      <circle cx="24" cy="24" r="14" fill="#38BDF8" fillOpacity="0.08" />

      {/* Interlocking dynamic flow paths representing manufacturing & promise schedule */}
      <g filter={`url(#${uid}-glow)`}>
        {/* Flow Path 1 - Lower pulse loop */}
        <path
          d="M13 28C13 23.5817 16.5817 20 21 20H27C31.4183 20 35 23.5817 35 28C35 32.4183 31.4183 36 27 36H20"
          stroke={`url(#${uid}-accent)`}
          strokeWidth="3.2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {/* Flow Path 2 - Upper precision loop */}
        <path
          d="M35 20C35 15.5817 31.4183 12 27 12H21C16.5817 12 13 15.5817 13 20"
          stroke={`url(#${uid}-primary)`}
          strokeWidth="3.2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {/* Dynamic Forward Delivery Arrow / Fast-Track */}
        <path
          d="M24 16L30 20L24 24"
          stroke="#67E8F9"
          strokeWidth="2.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {/* Active Node 1 - Emerald Commitment */}
        <circle cx="13" cy="28" r="3.2" fill="#10B981" />
        <circle cx="13" cy="28" r="1.5" fill="#ECFDF5" />

        {/* Active Node 2 - Cyan AI Node */}
        <circle cx="35" cy="20" r="3.2" fill="#38BDF8" />
        <circle cx="35" cy="20" r="1.5" fill="#FFFFFF" />

        {/* Center Synchronized Core */}
        <circle cx="24" cy="20" r="2.2" fill="#FFFFFF" />
      </g>
    </svg>
  );
}

/**
 * Complete Brand Logo with customizable text, AI badge, and MCCIA attribution.
 */
export function BrandLogo({
  className = "",
  size = 36,
  showText = true,
  title = "ProductionSaathi",
  subtitle = "MCCIA AI Studio",
  showAiBadge = true,
  theme = "dark",
  style = {},
  variant = "brand",
}: BrandLogoProps) {
  if (variant === "icon-only") {
    return <BrandIcon size={size} className={className} />;
  }

  const isLight = theme === "light";

  return (
    <div
      className={`brand-logo-container ${isLight ? "brand-light" : "brand-dark"} ${className}`.trim()}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: Math.max(8, Math.round(size * 0.28)),
        userSelect: "none",
        textDecoration: "none",
        ...style,
      }}
    >
      <BrandIcon size={size} />

      {showText && (
        <div style={{ display: "flex", flexDirection: "column", lineHeight: 1.15 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span
              style={{
                fontSize: Math.max(14, Math.round(size * 0.44)),
                fontWeight: 700,
                color: isLight ? "#0F172A" : "#F8FAFC",
                letterSpacing: "-0.4px",
                fontFamily: "var(--font-sans, system-ui, -apple-system, sans-serif)",
              }}
            >
              {title}
            </span>
            {showAiBadge && (
              <span
                style={{
                  fontSize: Math.max(9, Math.round(size * 0.25)),
                  fontWeight: 700,
                  letterSpacing: "0.6px",
                  padding: "2px 5px",
                  borderRadius: "4px",
                  background: isLight ? "rgba(37, 99, 235, 0.1)" : "rgba(56, 189, 248, 0.15)",
                  color: isLight ? "#2563EB" : "#38BDF8",
                  border: isLight ? "1px solid rgba(37, 99, 235, 0.25)" : "1px solid rgba(56, 189, 248, 0.3)",
                  lineHeight: 1,
                }}
              >
                AI
              </span>
            )}
          </div>
          {subtitle && (
            <span
              style={{
                fontSize: Math.max(10, Math.round(size * 0.28)),
                fontWeight: 500,
                color: isLight ? "#64748B" : "#94A3B8",
                letterSpacing: "0.2px",
                marginTop: 2,
              }}
            >
              {subtitle}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

export default BrandLogo;
