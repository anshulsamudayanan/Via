import type { ViaClient } from "@via/api-client";
import type { MeResponse, Page, Project } from "@via/types";
import { TooltipProvider } from "@via/ui";
import { render } from "@testing-library/react";
import type { ReactNode } from "react";
import { vi } from "vitest";

import { ApiProvider } from "@/components/api-context";
import { SessionContext } from "@/components/session";

export const me: MeResponse = {
  user: { id: "u1", email: "ada@example.com", display_name: "Ada Lovelace", email_verified_at: null, created_at: "2026-11-01T10:00:00Z" },
  organizations: [{ id: "o1", name: "Ada Lovelace's workspace", slug: "u-1", is_personal: true, role: "owner" }],
};

export function project(overrides: Partial<Project> = {}): Project {
  return {
    id: "p1",
    name: "Motor Controller",
    description: "BLDC driver",
    visibility: "private",
    organization: { id: "o1", name: "Ada Lovelace's workspace", is_personal: true },
    owner: { id: "u1", display_name: "Ada Lovelace" },
    my_role: "owner",
    design_count: 0,
    archived_at: null,
    created_at: "2026-11-01T10:00:00Z",
    updated_at: "2026-11-20T10:00:00Z",
    ...overrides,
  };
}

export function page<T>(items: T[], total = items.length): Page<T> {
  return { items, total, limit: 25, offset: 0 };
}

/** A client whose methods are all vi.fn(); override what a test needs. */
export function mockClient(overrides: Record<string, Record<string, unknown>> = {}): ViaClient {
  const base = {
    health: { live: vi.fn(), ready: vi.fn() },
    auth: { register: vi.fn(), login: vi.fn(), logout: vi.fn(), me: vi.fn(), sessions: vi.fn(), revokeSession: vi.fn(), requestPasswordReset: vi.fn(), confirmPasswordReset: vi.fn() },
    users: { updateMe: vi.fn(), changePassword: vi.fn() },
    organizations: { list: vi.fn(), create: vi.fn() },
    projects: { list: vi.fn(), summary: vi.fn(), get: vi.fn(), create: vi.fn(), update: vi.fn(), archive: vi.fn(), unarchive: vi.fn(), delete: vi.fn(), members: vi.fn(), addMember: vi.fn(), updateMember: vi.fn(), removeMember: vi.fn() },
    activity: { list: vi.fn().mockResolvedValue(page([])) },
    request: vi.fn(),
  } as Record<string, unknown>;
  for (const [k, v] of Object.entries(overrides)) base[k] = { ...(base[k] as object), ...v };
  return base as unknown as ViaClient;
}

export function renderWith(ui: ReactNode, client: ViaClient, session = true) {
  const sessionValue = { me, setMe: vi.fn(), signOut: vi.fn() };
  return render(
    <ApiProvider client={client}>
      <TooltipProvider>
        {session ? <SessionContext.Provider value={sessionValue}>{ui}</SessionContext.Provider> : ui}
      </TooltipProvider>
    </ApiProvider>,
  );
}

export const router = { push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), back: vi.fn(), forward: vi.fn(), prefetch: vi.fn() };
export const navigation = { search: new URLSearchParams(), pathname: "/" };
