"use client";

import type { ViaClient } from "@via/api-client";
import { createContext, type ReactNode, useContext } from "react";

import { api } from "@/lib/api";

const ApiContext = createContext<ViaClient>(api);

/** Override the API client (used by tests); the app uses the default client. */
export function ApiProvider({ client, children }: { client: ViaClient; children: ReactNode }) {
  return <ApiContext.Provider value={client}>{children}</ApiContext.Provider>;
}

export function useApi(): ViaClient {
  return useContext(ApiContext);
}
