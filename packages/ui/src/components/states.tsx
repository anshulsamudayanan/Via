import type { HTMLAttributes, ReactNode } from "react";

import { cn } from "../cn";

/** Placeholder block shown while content loads. Hidden from assistive tech. */
export function Skeleton({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div aria-hidden="true" className={cn("animate-pulse rounded-md bg-surface-hover", className)} {...props} />;
}

export function Spinner({ className, label = "Loading" }: { className?: string; label?: string }) {
  return (
    <span role="status" className={cn("inline-flex items-center", className)}>
      <span
        aria-hidden="true"
        className="size-4 animate-spin rounded-full border-2 border-border-strong border-t-accent"
      />
      <span className="sr-only">{label}</span>
    </span>
  );
}

interface StateProps {
  icon?: ReactNode;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}

/** Nothing here yet: explains why and offers the next step. */
export function EmptyState({ icon, title, description, action, className }: StateProps) {
  return (
    <div className={cn("flex flex-col items-center justify-center gap-2 px-6 py-10 text-center", className)}>
      {icon ? <div className="mb-1 text-subtle [&_svg]:size-6">{icon}</div> : null}
      <p className="text-sm font-medium text-foreground">{title}</p>
      {description ? <div className="max-w-sm text-xs text-muted">{description}</div> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}

/** Something went wrong: says what, and how to recover. Announced to screen readers. */
export function ErrorState({ icon, title, description, action, className }: StateProps) {
  return (
    <div
      role="alert"
      className={cn(
        "flex items-start gap-3 rounded-md border border-danger/30 bg-danger-soft px-3 py-2.5 text-sm",
        className,
      )}
    >
      {icon ? <div className="mt-0.5 text-danger [&_svg]:size-4">{icon}</div> : null}
      <div className="min-w-0 flex-1">
        <p className="font-medium text-foreground">{title}</p>
        {description ? <div className="mt-0.5 text-xs text-muted">{description}</div> : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}
