import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

import { navigation, router } from "./helpers";

vi.mock("next/navigation", () => ({
  useRouter: () => router,
  useSearchParams: () => navigation.search,
  usePathname: () => navigation.pathname,
  useParams: () => ({ projectId: "p1", designId: "d1" }),
}));

beforeEach(() => {
  navigation.search = new URLSearchParams();
  navigation.pathname = "/";
  for (const fn of Object.values(router)) fn.mockReset();
});

afterEach(cleanup);

// jsdom lacks these browser APIs used by the board viewer.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver;

/** Records path operations so renderer tests can inspect what would be drawn. */
class Path2DStub {
  ops: unknown[][] = [];
  moveTo(...a: number[]) { this.ops.push(["M", ...a]); }
  lineTo(...a: number[]) { this.ops.push(["L", ...a]); }
  arc(...a: number[]) { this.ops.push(["A", ...a]); }
  closePath() { this.ops.push(["Z"]); }
}
globalThis.Path2D ??= Path2DStub as unknown as typeof Path2D;

// Canvas has no 2D context in jsdom; return null quietly (the viewer then skips drawing).
HTMLCanvasElement.prototype.getContext = (() => null) as unknown as HTMLCanvasElement["getContext"];

// jsdom has no IntersectionObserver (Motion's whileInView / useInView use it): report every
// observed element as visible straight away, so in-view animations settle in tests.
class ImmediateIntersectionObserver {
  constructor(private readonly cb: IntersectionObserverCallback) {}
  observe(target: Element) {
    this.cb([{ isIntersecting: true, intersectionRatio: 1, target } as IntersectionObserverEntry], this as unknown as IntersectionObserver);
  }
  unobserve() {}
  disconnect() {}
  takeRecords() {
    return [];
  }
}
if (!("IntersectionObserver" in globalThis)) {
  (globalThis as unknown as { IntersectionObserver: unknown }).IntersectionObserver = ImmediateIntersectionObserver;
}

// jsdom has no matchMedia (hover-capability and theme checks use it): report "no match".
if (!window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}
