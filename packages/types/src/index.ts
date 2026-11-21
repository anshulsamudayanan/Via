/**
 * TypeScript mirror of the VIA API's response schemas.
 *
 * Hand-written for Stage 1 and kept in sync with apps/api (Pydantic models).
 * The API's OpenAPI document at /api/openapi.json is the source of truth.
 */

/** Every non-2xx API response. */
export interface ErrorResponse {
  error: {
    code: string;
    message: string;
    details: unknown;
    request_id: string | null;
  };
}

export type CheckStatus = "ok" | "error";

/** GET /api/v1/health */
export interface LivenessResponse {
  status: CheckStatus;
  version: string;
}

export interface CheckResult {
  status: CheckStatus;
  latency_ms: number;
  detail: string | null;
}

/** GET /api/v1/health/ready (200 when healthy, 503 with the same shape otherwise) */
export interface ReadinessResponse {
  status: CheckStatus;
  version: string;
  checks: Record<string, CheckResult>;
}

// ---------------------------------------------------------------- pagination

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

// ---------------------------------------------------------------- auth & users

export type OrganizationRole = "owner" | "admin" | "member";
export type ProjectRole = "owner" | "editor" | "viewer";
export type ProjectVisibility = "private" | "organization";

export interface User {
  id: string;
  email: string;
  display_name: string;
  email_verified_at: string | null;
  created_at: string;
}

export interface OrganizationSummary {
  id: string;
  name: string;
  slug: string;
  is_personal: boolean;
  role: OrganizationRole;
}

/** GET /api/v1/auth/me */
export interface MeResponse {
  user: User;
  organizations: OrganizationSummary[];
}

export interface SessionInfo {
  id: string;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  ip_address: string | null;
  user_agent: string | null;
  current: boolean;
}

export interface Message {
  message: string;
}

// ---------------------------------------------------------------- organizations & projects

export interface UserRef {
  id: string;
  display_name: string;
}

export interface Organization extends OrganizationSummary {
  created_at: string;
}

export interface Project {
  id: string;
  name: string;
  description: string;
  visibility: ProjectVisibility;
  organization: { id: string; name: string; is_personal: boolean };
  owner: UserRef;
  my_role: ProjectRole;
  design_count: number;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectSummary {
  active: number;
  archived: number;
}

export interface ProjectMember {
  user: UserRef;
  role: ProjectRole;
  added_at: string;
}

export type ProjectStatusFilter = "active" | "archived" | "all";
export type ProjectSort = "updated" | "created" | "name";

export interface ActivityItem {
  id: string;
  action: string;
  created_at: string;
  actor: UserRef | null;
  project: { id: string; name: string } | null;
  target_type: string | null;
  target_id: string | null;
  details: Record<string, unknown>;
}
