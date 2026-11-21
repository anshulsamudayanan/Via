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

// ---------------------------------------------------------------- designs & parsed PCB data

export type RevisionStatus = "pending" | "processing" | "ready" | "failed";

export interface DesignFile {
  id: string;
  kind: "source" | "normalized";
  original_filename: string | null;
  content_type: string;
  size_bytes: number;
  sha256: string;
  created_at: string;
  revision_id: string;
}

export interface ProjectFile extends DesignFile {
  design_id: string;
  design_name: string;
  revision_number: number;
}

export interface ParseWarning {
  code: string;
  message: string;
}

/** Stats computed by the PCB engine (see services/pcb-engine models.DesignStats). */
export interface DesignStats {
  layer_count: number;
  copper_layer_count: number;
  net_count: number;
  component_count: number;
  pad_count: number;
  smd_pad_count: number;
  through_hole_pad_count: number;
  track_count: number;
  via_count: number;
  zone_count: number;
  total_track_length: number;
  board_width: number | null;
  board_height: number | null;
  board_area: number | null;
  board_thickness: number | null;
  min_track_width: number | null;
  min_via_drill: number | null;
  min_via_diameter: number | null;
  components_top: number;
  components_bottom: number;
  unconnected_pad_count: number;
}

export interface Revision {
  id: string;
  design_id: string;
  project_id: string;
  revision_number: number;
  status: RevisionStatus;
  source_format: string;
  source_sha256: string;
  parser_version: string | null;
  schema_version: string | null;
  imported_at: string | null;
  error_code: string | null;
  error_message: string | null;
  warnings: ParseWarning[];
  /** Empty until parsed. */
  object_counts: Partial<DesignStats>;
  created_by: UserRef | null;
  created_at: string;
  source_file: DesignFile | null;
}

export interface Design {
  id: string;
  project_id: string;
  name: string;
  description: string;
  created_by: UserRef | null;
  created_at: string;
  updated_at: string;
  revision_count: number;
  current_revision: Revision | null;
  latest_revision: Revision | null;
}

export interface DesignDetail extends Design {
  revisions: Revision[];
}

export interface ImportResponse {
  design: Design;
  revision: Revision;
}

export interface UploadLimits {
  max_upload_bytes: number;
  formats: { id: string; name: string; extensions: string[] }[];
}

export interface BoardGeometry {
  outline_closed: boolean;
  min_x: number | null;
  min_y: number | null;
  max_x: number | null;
  max_y: number | null;
  width: number | null;
  height: number | null;
  area: number | null;
  thickness: number | null;
  copper_layer_count: number;
}

export interface BoardSummary {
  design: { id: string; name: string; project_id: string };
  revision: Revision;
  title: string | null;
  source: {
    format?: string;
    format_version?: string | null;
    generator?: string | null;
    generator_version?: string | null;
    filename?: string | null;
    size_bytes?: number;
  };
  constraints: Record<string, unknown>;
  geometry: BoardGeometry | null;
  stats: DesignStats;
  warnings: ParseWarning[];
}

export interface PcbComponent {
  id: string;
  reference: string;
  value: string | null;
  footprint: string;
  layer: string;
  side: string;
  x: number;
  y: number;
  rotation: number;
  pad_count: number;
  attributes: string[];
  properties: Record<string, string>;
}

export interface PcbNet {
  id: string;
  code: number;
  name: string;
  pad_count: number;
  track_count: number;
  via_count: number;
  track_length: number;
}

export interface PcbLayer {
  ordinal: number;
  name: string;
  kind: string;
  side: string;
  source_type: string | null;
  user_name: string | null;
}
