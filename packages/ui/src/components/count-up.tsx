"use client";

import { animate, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";

/**
 * A number that tweens on a spring from its previous value when the value changes (instant with
 * reduced motion). The first render shows the real value and never animates from 0, so nothing
 * ever reads as a false zero: during a change it only passes between two real values.
 */
export function CountUp({ value, className }: { value: number; className?: string }) {
  const reduce = useReducedMotion();
  const [shown, setShown] = useState(value);
  const previous = useRef(value);

  useEffect(() => {
    const from = previous.current;
    previous.current = value;
    if (from === value) return;
    if (reduce) {
      setShown(value);
      return;
    }
    const controls = animate(from, value, { type: "spring", stiffness: 120, damping: 24, onUpdate: (v) => setShown(Math.round(v)) });
    return () => {
      controls.stop();
      setShown(value);
    };
  }, [value, reduce]);

  // One text node, so assistive tech and copy/paste read a real number.
  return <span className={className}>{shown}</span>;
}
