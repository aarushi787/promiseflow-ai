import type { CSSProperties } from "react";
import { BrandIcon, BrandLogo } from "./BrandLogo";

export { BrandIcon, BrandLogo };

interface McciaLogoProps {
  className?: string;
  height?: number | string;
  alt?: string;
  style?: CSSProperties;
  variant?: "brand" | "mccia" | "icon";
  inverted?: boolean;
}

/**
 * Universal logo component supporting both crisp SVG PromiseFlow brand icon
 * and clean MCCIA partner emblem.
 */
export function McciaLogo({
  className = "",
  height = 28,
  alt = "MCCIA Manufacturing Intelligence",
  style = {},
  variant = "brand",
}: McciaLogoProps) {
  const numericHeight =
    typeof height === "number" ? height : parseInt(String(height), 10) || 28;

  if (variant === "brand") {
    return <BrandIcon size={numericHeight + 6} className={className} />;
  }

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
        const target = e.currentTarget as HTMLImageElement;
        if (!target.src.endsWith("mccia-logo.svg")) {
          target.src = "/mccia-logo.svg";
        }
      }}
    />
  );
}

export function McciaMark({ size = 32 }: { size?: number }) {
  return <BrandIcon size={size} />;
}

export default McciaLogo;
