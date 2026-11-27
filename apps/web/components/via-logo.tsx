/** VIA wordmark: a plated via (ring + drill) followed by the name. `compact` shows the mark only. */
export function ViaLogo({ className, compact = false }: { className?: string; compact?: boolean }) {
  return (
    <span className={`inline-flex items-center gap-2 ${className ?? ""}`}>
      <svg viewBox="0 0 20 20" className="size-5" aria-hidden="true">
        <circle cx="10" cy="10" r="8" fill="none" stroke="currentColor" strokeWidth="2.5" className="text-accent" />
        <circle cx="10" cy="10" r="3" fill="currentColor" className="text-foreground" />
      </svg>
      {compact ? <span className="sr-only">VIA</span> : <span className="font-display text-[17px] font-bold tracking-[0.02em] text-foreground">VIA</span>}
    </span>
  );
}
