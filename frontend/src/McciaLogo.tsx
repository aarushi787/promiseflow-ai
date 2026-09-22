import type { CSSProperties } from "react";

interface McciaLogoProps {
  className?: string;
  height?: number | string;
  alt?: string;
  style?: CSSProperties;
  inverted?: boolean;
}

export function McciaLogo({
  className = "",
  height = 28,
  alt = "MCCIA - Mahratta Chamber of Commerce, Industries and Agriculture",
  style = {},
}: McciaLogoProps) {
  const numericHeight = typeof height === "number" ? height : parseInt(String(height), 10) || 28;

  return (
    <img
      src="/mccia-logo.png"
      alt={alt}
      className={`mccia-logo ${className}`.trim()}
      style={{
        height: numericHeight,
        width: "auto",
        display: "inline-block",
        verticalAlign: "middle",
        objectFit: "contain",
        flexShrink: 0,
        ...style,
      }}
      onError={(e) => {
        // Fallback to SVG asset if PNG fails
        const target = e.currentTarget as HTMLImageElement;
        if (!target.src.endsWith("mccia-logo.svg")) {
          target.src = "/mccia-logo.svg";
        }
      }}
    />
  );
}

export function McciaMark({ size = 32 }: { size?: number }) {
  return (
    <span
      className="mccia-mark-badge"
      style={{
        width: size,
        height: size,
        borderRadius: Math.round(size * 0.22),
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        background: "#FFFFFF",
        padding: Math.max(2, Math.round(size * 0.1)),
        boxShadow: "0 2px 6px rgba(0, 0, 0, 0.12)",
        flexShrink: 0,
        overflow: "hidden",
      }}
    >
      <img
        src="/mccia-logo.png"
        alt="MCCIA"
        style={{
          width: "100%",
          height: "100%",
          objectFit: "contain",
        }}
      />
    </span>
  );
}

export default McciaLogo;
