import type { ViaClient } from "@via/api-client";
import type { DesignDetail, MeResponse, Page, Project, Revision } from "@via/types";
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

export function revision(overrides: Partial<Revision> = {}): Revision {
  return {
    id: "r1", design_id: "d1", project_id: "p1", revision_number: 1, status: "ready", source_format: "kicad",
    source_sha256: "a".repeat(64), parser_version: "0.1.0", schema_version: "1.0.0", imported_at: "2026-11-21T10:00:00Z",
    error_code: null, error_message: null, warnings: [],
    object_counts: { component_count: 4, net_count: 3, layer_count: 18, copper_layer_count: 2 },
    created_by: { id: "u1", display_name: "Ada Lovelace" }, created_at: "2026-11-21T10:00:00Z",
    source_file: { id: "f1", kind: "source", original_filename: "board.kicad_pcb", content_type: "application/octet-stream", size_bytes: 512, sha256: "a".repeat(64), created_at: "2026-11-21T10:00:00Z", revision_id: "r1" },
    ...overrides,
  };
}

export function design(overrides: Partial<DesignDetail> = {}): DesignDetail {
  const rev = revision();
  return {
    id: "d1", project_id: "p1", name: "Motor board", description: "", created_by: { id: "u1", display_name: "Ada Lovelace" },
    created_at: "2026-11-21T10:00:00Z", updated_at: "2026-11-21T10:00:00Z", revision_count: 1,
    current_revision: rev, latest_revision: rev, revisions: [rev], ...overrides,
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
    designs: { list: vi.fn().mockResolvedValue([]), get: vi.fn(), update: vi.fn(), delete: vi.fn() },
    revisions: { get: vi.fn() },
    files: { list: vi.fn().mockResolvedValue([]), downloadUrl: (id: string) => `/api/v1/files/${id}/download` },
    pcb: {
      limits: vi.fn().mockResolvedValue({ max_upload_bytes: 1024, formats: [{ id: "kicad", name: "KiCad PCB", extensions: [".kicad_pcb"] }] }),
      summary: vi.fn(), components: vi.fn(), nets: vi.fn(), layers: vi.fn(), upload: vi.fn(), normalized: vi.fn().mockReturnValue(new Promise(() => {})),
    },
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
