"use client";

import type { Revision } from "@via/types";
import { useEffect, useState } from "react";

import { useApi } from "@/components/api-context";
import { isTerminal } from "@/components/designs/revision-status";

/** Poll a revision until it's parsed or failed. */
export function useRevisionPoll(initial: Revision | null, intervalMs = 1500): Revision | null {
  const client = useApi();
  const [revision, setRevision] = useState<Revision | null>(initial);
  const id = initial?.id;

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset when the tracked revision changes
    setRevision(initial);
    if (!initial || isTerminal(initial.status)) return;
    const ac = new AbortController();
    let timer: number | undefined;
    const tick = async () => {
      try {
        const next = await client.revisions.get(initial.id, ac.signal);
        setRevision(next);
        if (isTerminal(next.status)) return;
      } catch (err) {
        if (ac.signal.aborted) return;
        void err; // transient errors: keep polling
      }
      timer = window.setTimeout(() => void tick(), intervalMs);
    };
    timer = window.setTimeout(() => void tick(), intervalMs);
    return () => {
      ac.abort();
      window.clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- restart only for a different revision
  }, [client, id, intervalMs]);

  return revision;
}
