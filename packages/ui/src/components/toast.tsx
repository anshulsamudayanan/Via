"use client";

import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";
import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

import { cn } from "../cn";

export type ToastTone = "info" | "success" | "error";

export interface ToastOptions {
  title: string;
  description?: ReactNode;
  tone?: ToastTone;
  /** A link or button shown under the text, e.g. "Open design". */
  action?: ReactNode;
  /** Milliseconds before it closes itself; 0 keeps it until dismissed. Default 5000 (errors 8000). */
  duration?: number;
}

interface ToastItem extends ToastOptions {
  id: number;
}

type Push = (t: ToastOptions) => number;
const ToastContext = createContext<{ push: Push; dismiss: (id: number) => void } | null>(null);

const ICON: Record<ToastTone, ReactNode> = {
  info: <Info className="text-muted" aria-hidden="true" />,
  success: <CheckCircle2 className="text-success" aria-hidden="true" />,
  error: <AlertCircle className="text-danger" aria-hidden="true" />,
};

/** Small, dependency-free toasts: polite live region, pause on hover or focus, at most three on screen. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const nextId = useRef(1);
  const dismiss = useCallback((id: number) => setItems((l) => l.filter((t) => t.id !== id)), []);
  const push = useCallback<Push>((t) => {
    const id = nextId.current++;
    setItems((l) => [...l.slice(-2), { ...t, id }]);
    return id;
  }, []);
  const value = useMemo(() => ({ push, dismiss }), [push, dismiss]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <section
        aria-label="Notifications"
        className="pointer-events-none fixed inset-x-0 bottom-0 z-[60] flex flex-col items-center gap-2 p-4 sm:inset-x-auto sm:right-0 sm:items-end"
      >
        {items.length ? (
          <ol className="flex w-full flex-col gap-2 sm:w-[360px]">
            {items.map((t) => (
              <ToastView key={t.id} toast={t} onDismiss={() => dismiss(t.id)} />
            ))}
          </ol>
        ) : null}
      </section>
    </ToastContext.Provider>
  );
}

function ToastView({ toast, onDismiss }: { toast: ToastItem; onDismiss: () => void }) {
  const tone = toast.tone ?? "info";
  const duration = toast.duration ?? (tone === "error" ? 8000 : 5000);
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    if (!duration || paused) return;
    const t = window.setTimeout(onDismiss, duration);
    return () => window.clearTimeout(t);
  }, [duration, paused, onDismiss]);

  return (
    <li
      role={tone === "error" ? "alert" : "status"}
      aria-atomic="true"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)}
      onBlur={() => setPaused(false)}
      className="pointer-events-auto flex animate-overlay-in gap-2.5 rounded-lg border border-border bg-surface-raised p-3 shadow-overlay motion-reduce:animate-none [&>svg]:mt-px [&>svg]:size-4 [&>svg]:shrink-0"
    >
      {ICON[tone]}
      <div className="min-w-0 flex-1">
        <p className="text-[13px] font-medium leading-5 text-foreground">{toast.title}</p>
        {toast.description ? <div className="mt-0.5 break-words text-xs text-muted">{toast.description}</div> : null}
        {toast.action ? <div className="mt-2 text-xs">{toast.action}</div> : null}
      </div>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss notification"
        className={cn("-m-1 flex size-6 shrink-0 items-center justify-center rounded-md text-subtle hover:bg-surface-hover hover:text-foreground [&>svg]:size-3.5")}
      >
        <X aria-hidden="true" />
      </button>
    </li>
  );
}

/** `toast({ title, tone })` from anywhere under ToastProvider. */
export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside <ToastProvider>");
  return ctx;
}
