"use client";

import type { ComponentProps } from "react";

import LiquidGlassButton from "@/components/originkit/light-glass-button";
import { useTheme } from "@/lib/use-theme";

type Size = "md" | "lg";

const PADDING: Record<Size, string> = { md: "9px 18px", lg: "13px 26px" };
const FONT: Record<Size, number> = { md: 13.5, lg: 15.5 };

type Props = Omit<ComponentProps<typeof LiquidGlassButton>, "font" | "padding" | "colors" | "light" | "stroke" | "rounded"> & {
  size?: Size;
};

/**
 * VIA's primary call to action: Originkit's Light Glass Button with VIA's recipe baked in: a pill,
 * a purple cursor-tracked light, a white-to-violet gradient ring, the UI font. It renders a real
 * <button> (or a Next <Link>/<a> with `link`), so focus, keyboard and the global focus ring work.
 */
export function GlassCta({ size = "md", newTab = false, className, ...props }: Props) {
  const dark = useTheme() !== "light";
  return (
    <LiquidGlassButton
      rounded={100}
      newTab={newTab}
      padding={PADDING[size]}
      font={{ fontFamily: "var(--font-sans)", fontWeight: 600, fontSize: FONT[size], letterSpacing: "-0.01em", whiteSpace: "nowrap" }}
      colors={
        dark
          ? { fill: "#ad9be4", textColor: "#ffffff", hoverFill: "#bcadea", hoverTextColor: "#ffffff" }
          : { fill: "#5e4d93", textColor: "#1c1530", hoverFill: "#6b59a3", hoverTextColor: "#0f0b1c" }
      }
      light={{ color: dark ? "rgba(190, 170, 255, 0.75)" : "rgba(94, 77, 147, 0.45)", size: 55, intensity: 100, smoothness: 70 }}
      stroke={{
        type: "gradient",
        width: size === "lg" ? 2 : 1.5,
        colorA: dark ? "rgba(255, 255, 255, 0.6)" : "rgba(94, 77, 147, 0.55)",
        colorB: dark ? "rgba(173, 155, 228, 0.35)" : "rgba(94, 77, 147, 0.2)",
        angle: 160,
      }}
      className={["disabled:pointer-events-none disabled:opacity-50", className].filter(Boolean).join(" ")}
      {...props}
    />
  );
}
