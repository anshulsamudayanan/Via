"use client";

import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { m, useReducedMotion } from "motion/react";
import type { ComponentProps, ReactNode } from "react";

import { cn } from "../cn";
import { SPRING } from "../motion";

export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;
export const DialogClose = DialogPrimitive.Close;

interface DialogContentProps extends ComponentProps<typeof DialogPrimitive.Content> {
  title: string;
  description?: ReactNode;
  footer?: ReactNode;
  /** Render only the children (title kept for screen readers): for search-style dialogs. */
  bare?: boolean;
}

/** Modal dialog with focus trap, Escape to close and labelled title/description. */
export function DialogContent({ title, description, footer, bare = false, className, children, ...props }: DialogContentProps) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-black/50 backdrop-blur-[2px] data-[state=open]:animate-fade-in" />
      <DialogPrimitive.Content
        className={cn(
          "glass-overlay fixed left-1/2 top-[12vh] z-50 w-[calc(100vw-2rem)] max-w-md -translate-x-1/2 rounded-3xl data-[state=open]:animate-overlay-in data-[state=closed]:animate-overlay-out",
          "focus-visible:outline-none",
          className,
        )}
        {...(description ? {} : { "aria-describedby": undefined })}
        {...props}
      >
        {bare ? (
          <>
            <DialogPrimitive.Title className="sr-only">{title}</DialogPrimitive.Title>
            {children}
          </>
        ) : (
          <>
            <div className="flex items-start justify-between gap-3 border-b border-border px-5 py-4">
              <div className="space-y-0.5">
                <DialogPrimitive.Title className="text-[15px] font-semibold tracking-tight">{title}</DialogPrimitive.Title>
                {description ? (
                  <DialogPrimitive.Description className="text-xs text-muted">{description}</DialogPrimitive.Description>
                ) : null}
              </div>
              <DialogPrimitive.Close
                className="rounded-full p-1.5 text-muted hover:bg-surface-hover hover:text-foreground"
                aria-label="Close"
              >
                <X className="size-4" />
              </DialogPrimitive.Close>
            </div>
            <div className="px-5 py-5">{children}</div>
            {footer ? <div className="flex justify-end gap-2 border-t border-border px-5 py-3.5">{footer}</div> : null}
          </>
        )}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}

interface MotionDialogContentProps extends Omit<ComponentProps<typeof DialogPrimitive.Content>, "asChild" | "forceMount"> {
  /** Accessible name (visually hidden): the content supplies its own visible UI. */
  title: string;
}

/**
 * Dialog content for use inside <AnimatePresence>: overlay fades, the panel opens from scale 0.96
 * with a blur (iOS sheet feel) and reverses on close. Render it only while open.
 */
export function MotionDialogContent({ title, className, children, ...props }: MotionDialogContentProps) {
  const reduce = useReducedMotion();
  return (
    <DialogPrimitive.Portal forceMount>
      <DialogPrimitive.Overlay forceMount asChild>
        <m.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.18 }} className="fixed inset-0 z-40 bg-black/45" />
      </DialogPrimitive.Overlay>
      <DialogPrimitive.Content forceMount asChild aria-describedby={undefined} {...props}>
        <m.div
          initial={reduce ? { opacity: 0 } : { opacity: 0, scale: 0.96, filter: "blur(8px)" }}
          animate={{ opacity: 1, scale: 1, filter: "blur(0px)" }}
          exit={reduce ? { opacity: 0 } : { opacity: 0, scale: 0.97, filter: "blur(6px)" }}
          transition={SPRING}
          className={cn("glass-overlay fixed left-1/2 top-[12vh] z-50 w-[calc(100vw-2rem)] max-w-md overflow-hidden rounded-[26px] focus-visible:outline-none", className)}
          style={{ x: "-50%" }}
        >
          <DialogPrimitive.Title className="sr-only">{title}</DialogPrimitive.Title>
          {children}
        </m.div>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}
