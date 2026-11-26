"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback } from "react";

/**
 * List-page state kept in the URL (shareable, survives reloads). `update` replaces the given keys;
 * null or "" removes one. Any change other than `page` resets to the first page.
 */
export function useUrlParams() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const update = useCallback(
    (changes: Record<string, string | null>) => {
      const next = new URLSearchParams(params.toString());
      for (const [k, v] of Object.entries(changes)) {
        if (v === null || v === "") next.delete(k);
        else next.set(k, v);
      }
      if (!("page" in changes)) next.delete("page");
      const s = next.toString();
      router.replace(s ? `${pathname}?${s}` : pathname, { scroll: false });
    },
    [params, pathname, router],
  );
  const page = Math.max(0, Number.parseInt(params.get("page") ?? "0", 10) || 0);
  return { params, update, page };
}

export function pick<T extends string>(value: string | null, allowed: readonly T[], fallback: T): T {
  return allowed.includes(value as T) ? (value as T) : fallback;
}
