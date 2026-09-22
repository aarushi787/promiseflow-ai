import type { CSSProperties } from "react";

interface McciaLogoProps {
  className?: string;
  height?: number | string;
  alt?: string;
  style?: CSSProperties;
  badge?: boolean;
}

/**
 * Official MCCIA corporate logo component.
 * Renders the authentic Mahratta Chamber of Commerce, Industries and Agriculture emblem.
 */
export function McciaLogo({
  className = "",
  height = 28,
  alt = "MCCIA - Mahratta Chamber of Commerce, Industries and Agriculture",
  style = {},
  badge = false,
}: McciaLogoProps) {
  const numericHeight =
    typeof height === "number" ? height : parseInt(String(height), 10) || 28;

  const image = (
    <img
      src="/mccia-logo.png"
      alt={alt}
      className={`mccia-logo-img ${className}`.trim()}
      style={{
        height: numericHeight,
        width: "auto",
        display: "block",
        objectFit: "contain",
        flexShrink: 0,
        imageRendering: "auto",
        ...style,
      }}
      onError={(e) => {
        const target = e.currentTarget as HTMLImageElement;
        if (!target.src.endsWith("mccia-logo-solid.png")) {
          target.src = "/mccia-logo-solid.png";
        }
      }}
    />
  );

  if (badge) {
    return (
      <span
        className="mccia-logo-badge"
        style={{
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#FFFFFF",
          padding: "6px 12px",
          borderRadius: "8px",
          boxShadow: "0 2px 8px rgba(0, 0, 0, 0.12)",
          border: "1px solid rgba(255, 255, 255, 0.2)",
          flexShrink: 0,
        }}
      >
        {image}
      </span>
    );
  }

  return image;
}

/**
 * Compact MCCIA Badge for icons and avatar marks.
 */
export function McciaMark({ size = 32 }: { size?: number }) {
  return (
    <span
      className="mccia-mark-badge"
      style={{
        width: size,
        height: size,
        borderRadius: Math.round(size * 0.25),
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        background: "#FFFFFF",
        padding: Math.max(3, Math.round(size * 0.12)),
        boxShadow: "0 2px 8px rgba(0, 0, 0, 0.15)",
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
