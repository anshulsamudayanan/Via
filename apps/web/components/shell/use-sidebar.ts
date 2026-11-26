"use client";

import { useSyncExternalStore } from "react";

const KEY = "via-sidebar-collapsed";
const listeners = new Set<() => void>();
let state: boolean | null = null;

function read(): boolean {
  if (state === null) {
    try {
      const saved = localStorage.getItem(KEY);
      // No saved choice: start collapsed on tablet widths, expanded on desktop.
      state = saved === null ? window.matchMedia("(max-width: 1279px)").matches : saved === "1";
    } catch {
      state = false;
    }
  }
  return state;
}

function subscribe(fn: () => void) {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

export function setSidebarCollapsed(next: boolean) {
  state = next;
  try {
    localStorage.setItem(KEY, next ? "1" : "0");
  } catch {
    // Storage unavailable (private mode): the choice lasts for this page only.
  }
  listeners.forEach((l) => l());
}

/** Desktop sidebar collapse, remembered per browser. The server render assumes expanded. */
export function useSidebarCollapsed(): boolean {
  return useSyncExternalStore(subscribe, read, () => false);
}
