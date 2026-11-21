/** VIA wordmark: a plated via (ring + drill) followed by the name. */
export function ViaLogo({ className }: { className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2 ${className ?? ""}`}>
      <svg viewBox="0 0 20 20" className="size-5" aria-hidden="true">
        <circle cx="10" cy="10" r="8" fill="none" stroke="currentColor" strokeWidth="2.5" className="text-accent" />
        <circle cx="10" cy="10" r="3" fill="currentColor" className="text-foreground" />
      </svg>
      <span className="text-[15px] font-semibold tracking-tight text-foreground">VIA</span>
    </span>
  );
}
