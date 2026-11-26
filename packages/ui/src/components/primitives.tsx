import type { HTMLAttributes, ReactNode } from "react";

import { cn } from "../cn";

/** Keyboard key hint, e.g. <Kbd>⌘K</Kbd>. */
export function Kbd({ className, ...props }: HTMLAttributes<HTMLElement>) {
  return (
    <kbd
      className={cn(
        "inline-flex h-5 min-w-5 items-center justify-center rounded-sm border border-border bg-surface-sunken px-1 font-mono text-[11px] leading-none text-subtle",
        className,
      )}
      {...props}
    />
  );
}

/** Engineering identifiers only: references, net names, measurements, file names, revision numbers. */
export function Mono({ className, ...props }: HTMLAttributes<HTMLSpanElement>) {
  return <span className={cn("font-mono text-[12.5px] tabular-nums", className)} {...props} />;
}

interface PanelProps extends Omit<HTMLAttributes<HTMLElement>, "title"> {
  title?: ReactNode;
  /** Short context next to the title (counts, scope). */
  meta?: ReactNode;
  /** Controls on the right of the header row. */
  actions?: ReactNode;
  /** Optional footer row (pagination, "view all"). */
  footer?: ReactNode;
}

/** Flat bordered region with a 40 px header row. Renders a <section> labelled by its title. */
export function Panel({ title, meta, actions, footer, className, children, ...props }: PanelProps) {
  return (
    <section className={cn("min-w-0 rounded-lg border border-border bg-surface", className)} {...props}>
      {title || actions ? (
        <header className="flex min-h-10 flex-wrap items-center gap-x-3 gap-y-1 border-b border-border px-4 py-1.5">
          {title ? <h2 className="text-[13px] font-semibold text-foreground">{title}</h2> : null}
          {meta ? <span className="text-xs text-subtle tabular-nums">{meta}</span> : null}
          {actions ? <div className="ml-auto flex items-center gap-2">{actions}</div> : null}
        </header>
      ) : null}
      {children}
      {footer ? (
        <footer className="flex min-h-9 items-center justify-between gap-3 border-t border-border px-4 py-1.5 text-xs text-subtle">
          {footer}
        </footer>
      ) : null}
    </section>
  );
}
