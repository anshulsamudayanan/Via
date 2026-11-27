"use client";

import { m } from "motion/react";
import { type KeyboardEvent, type ReactNode, useId, useRef } from "react";

import { cn } from "../cn";
import { SPRING } from "../motion";

export interface Segment<T extends string> {
  value: T;
  label: string;
  /** Icon-only segments show the label as the accessible name and tooltip. */
  icon?: ReactNode;
}

interface Props<T extends string> {
  value: T;
  onChange: (value: T) => void;
  segments: Segment<T>[];
  "aria-label": string;
  /** Show icons only (label becomes the accessible name). */
  iconOnly?: boolean;
  className?: string;
}

/**
 * iOS-style segmented control: a glass thumb slides between options on a spring (shared layoutId).
 * A radiogroup with roving focus: arrow keys move and select, Home/End jump.
 */
export function SegmentedControl<T extends string>({ value, onChange, segments, iconOnly = false, className, ...aria }: Props<T>) {
  const id = useId();
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  function onKeyDown(e: KeyboardEvent, i: number) {
    const last = segments.length - 1;
    const next = e.key === "ArrowRight" || e.key === "ArrowDown" ? (i === last ? 0 : i + 1) : e.key === "ArrowLeft" || e.key === "ArrowUp" ? (i === 0 ? last : i - 1) : e.key === "Home" ? 0 : e.key === "End" ? last : -1;
    if (next < 0) return;
    e.preventDefault();
    onChange(segments[next]!.value);
    refs.current[next]?.focus();
  }

  return (
    <div role="radiogroup" aria-label={aria["aria-label"]} className={cn("relative inline-flex h-8 items-center rounded-full bg-surface-sunken p-0.5 ring-1 ring-border ring-inset", className)}>
      {segments.map((s, i) => {
        const active = s.value === value;
        return (
          <button
            key={s.value}
            ref={(el) => {
              refs.current[i] = el;
            }}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={iconOnly ? s.label : undefined}
            title={iconOnly ? s.label : undefined}
            tabIndex={active ? 0 : -1}
            onClick={() => onChange(s.value)}
            onKeyDown={(e) => onKeyDown(e, i)}
            className={cn(
              "relative z-10 flex h-7 items-center justify-center gap-1.5 rounded-full text-xs font-medium transition-colors duration-150 [&_svg]:size-3.5",
              iconOnly ? "w-8" : "px-3",
              active ? "text-foreground" : "text-muted hover:text-foreground",
            )}
          >
            {active ? (
              <m.span
                layoutId={`seg-${id}`}
                transition={SPRING}
                aria-hidden="true"
                className="absolute inset-0 -z-10 rounded-full bg-surface-raised shadow-[inset_0_1px_0_var(--via-glass-highlight),0_2px_8px_rgb(0_0_0/0.25)] ring-1 ring-border-strong"
              />
            ) : null}
            {s.icon}
            {iconOnly ? null : s.label}
          </button>
        );
      })}
    </div>
  );
}
