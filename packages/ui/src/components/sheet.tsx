"use client";

import * as DialogPrimitive from "@radix-ui/react-dialog";
import type { ComponentProps, ReactNode } from "react";

import { cn } from "../cn";

export const Sheet = DialogPrimitive.Root;
export const SheetTrigger = DialogPrimitive.Trigger;
export const SheetClose = DialogPrimitive.Close;

interface SheetContentProps extends ComponentProps<typeof DialogPrimitive.Content> {
  /** Accessible name (visually hidden): the sheet's content supplies its own visible heading. */
  title: string;
  side?: "left" | "right";
  children: ReactNode;
}

/** Edge drawer (mobile navigation) with focus trap and Escape to close. */
export function SheetContent({ title, side = "left", className, children, ...props }: SheetContentProps) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-black/50 data-[state=open]:animate-fade-in" />
      <DialogPrimitive.Content
        aria-describedby={undefined}
        className={cn(
          "glass-thick fixed inset-y-2 z-50 flex w-[min(18rem,85vw)] flex-col rounded-3xl focus-visible:outline-none",
          side === "left"
            ? "left-2 data-[state=open]:animate-[via-sheet-in-left_180ms_cubic-bezier(0.2,0,0,1)]"
            : "right-2 data-[state=open]:animate-[via-sheet-in-right_180ms_cubic-bezier(0.2,0,0,1)]",
          className,
        )}
        {...props}
      >
        <DialogPrimitive.Title className="sr-only">{title}</DialogPrimitive.Title>
        {children}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}
