import { cn } from "../cn";

const tones = {
  ok: "bg-success",
  warning: "bg-warning",
  error: "bg-danger",
  unknown: "bg-subtle",
} as const;

export type StatusTone = keyof typeof tones;

/** A small coloured dot. Always pair with a text label; colour alone is not accessible. */
export function StatusDot({ tone, className }: { tone: StatusTone; className?: string }) {
  return <span aria-hidden="true" className={cn("inline-block size-2 shrink-0 rounded-full", tones[tone], className)} />;
}
