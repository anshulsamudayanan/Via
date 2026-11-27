"use client";

import { animate, useInView, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";

/**
 * A number that counts up on a spring the first time it scrolls into view (instant with reduced
 * motion). Until then it shows the real value, so nothing ever reads as a false zero.
 */
export function CountUp({ value, className }: { value: number; className?: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true });
  const reduce = useReducedMotion();
  const [shown, setShown] = useState(value);

  useEffect(() => {
    if (!inView) return;
    if (reduce || value === 0) {
      setShown(value);
      return;
    }
    const controls = animate(0, value, { type: "spring", stiffness: 120, damping: 24, onUpdate: (v) => setShown(Math.round(v)) });
    return () => controls.stop();
  }, [inView, value, reduce]);

  return (
    // One text node: the count settles on the real value within a second, and before the element is
    // in view it already shows that value, so assistive tech and copy/paste read the true number.
    <span ref={ref} className={className}>
      {shown}
    </span>
  );
}
