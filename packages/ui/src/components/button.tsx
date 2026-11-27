"use client";

import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { type HTMLMotionProps, m } from "motion/react";
import type { ButtonHTMLAttributes, Ref } from "react";

import { cn } from "../cn";
import { SPRING_PRESS } from "../motion";

export const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-1.5 whitespace-nowrap rounded-full font-medium tracking-[-0.01em] transition-[background-color,color,box-shadow,border-color] duration-150 " +
    "disabled:pointer-events-none disabled:opacity-50 [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        // Glowing purple glass pill.
        primary: "bg-accent/90 text-accent-foreground shadow-glow hover:bg-accent",
        // Clear glass pill: tinted fill, hairline, top highlight (no blur of its own: blur budget).
        secondary:
          "border border-border-strong bg-surface text-foreground shadow-[inset_0_1px_0_var(--via-glass-highlight)] hover:border-subtle/40 hover:bg-surface-hover",
        ghost: "text-muted hover:bg-surface-hover hover:text-foreground",
        danger: "border border-danger/40 bg-danger-soft text-danger hover:bg-danger hover:text-white",
      },
      size: {
        sm: "h-7 px-3 text-xs",
        md: "h-8 px-3.5 text-[13px]",
        lg: "h-10 px-5 text-[15px]",
        icon: "size-8",
      },
    },
    defaultVariants: { variant: "secondary", size: "md" },
  },
);

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  /** Render the child element (e.g. a link) with button styling. */
  asChild?: boolean;
  ref?: Ref<HTMLButtonElement>;
}

/** Pill button with spring press-down feedback (scale 0.97). */
export function Button({ className, variant, size, asChild = false, type, ...props }: ButtonProps) {
  const classes = cn(buttonVariants({ variant, size }), className);
  if (asChild) {
    // Links styled as buttons: CSS press feedback (Slot can't host a motion component).
    return <Slot className={cn(classes, "transition-transform active:scale-[0.97]")} {...props} />;
  }
  return <m.button whileTap={{ scale: 0.97 }} transition={SPRING_PRESS} className={classes} type={type ?? "button"} {...(props as HTMLMotionProps<"button">)} />;
}
