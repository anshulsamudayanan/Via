"use client";

import { ApiError } from "@via/api-client";
import type { MeResponse } from "@via/types";
import { Button, ErrorState, Spinner } from "@via/ui";
import { usePathname, useRouter } from "next/navigation";
import { createContext, type ReactNode, useCallback, useContext, useEffect, useState } from "react";

import { useApi } from "@/components/api-context";

interface SessionValue {
  me: MeResponse;
  setMe: (me: MeResponse) => void;
  signOut: () => Promise<void>;
}

/** Exported for tests; the app always goes through <SessionProvider>. */
export const SessionContext = createContext<SessionValue | null>(null);

export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession must be used inside <SessionProvider>");
  return value;
}

type State = { kind: "loading" } | { kind: "ready"; me: MeResponse } | { kind: "error"; error: unknown };

/**
 * Guards the signed-in area. The API is the source of truth: if /auth/me
 * returns 401 the user is sent to the login page (with a safe `next`).
 */
export function SessionProvider({ children }: { children: ReactNode }) {
  const client = useApi();
  const router = useRouter();
  const pathname = usePathname();
  const [state, setState] = useState<State>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const ac = new AbortController();
    client.auth
      .me(ac.signal)
      .then((me) => setState({ kind: "ready", me }))
      .catch((error: unknown) => {
        if (ac.signal.aborted) return;
        if (error instanceof ApiError && error.status === 401) {
          router.replace(`/login?next=${encodeURIComponent(pathname)}`);
          return;
        }
        setState({ kind: "error", error });
      });
    return () => ac.abort();
    // Only re-check on mount / explicit retry, not on every navigation.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client, attempt]);

  const signOut = useCallback(async () => {
    try {
      await client.auth.logout();
    } finally {
      router.replace("/login");
      router.refresh();
    }
  }, [client, router]);

  const setMe = useCallback((me: MeResponse) => setState({ kind: "ready", me }), []);

  if (state.kind === "loading") {
    return (
      <div className="flex min-h-dvh items-center justify-center">
        <Spinner label="Checking your session" />
      </div>
    );
  }
  if (state.kind === "error") {
    return (
      <div className="mx-auto mt-24 max-w-md px-4">
        <ErrorState
          title="We couldn't load your account"
          description="The VIA API is unreachable or returned an error."
          action={
            <Button size="sm" onClick={() => setAttempt((a) => a + 1)}>
              Retry
            </Button>
          }
        />
      </div>
    );
  }
  return <SessionContext.Provider value={{ me: state.me, setMe, signOut }}>{children}</SessionContext.Provider>;
}
