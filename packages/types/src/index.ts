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

// ---------------------------------------------------------------- normalized PCB model
// Mirror of services/pcb-engine/src/via_pcb/models (schema 1.x). Millimetres,
// degrees (CCW on screen, normalized to [0, 360)), absolute board coordinates,
// KiCad's +Y-down axis.

export interface Point {
  x: number;
  y: number;
}

export interface BoundingBox {
  min_x: number;
  min_y: number;
  max_x: number;
  max_y: number;
}

export type LayerKind =
  | "copper" | "silkscreen" | "solder_mask" | "solder_paste" | "adhesive" | "fabrication"
  | "courtyard" | "edge" | "margin" | "documentation" | "user";
export type Side = "top" | "bottom" | "inner" | "none";

export interface PcbLayerDef {
  index: number;
  name: string;
  kind: LayerKind;
  side: Side;
  source_type: string | null;
  user_name: string | null;
}

export interface Graphic {
  kind: "line" | "arc" | "circle" | "rect" | "polygon";
  layer: string;
  width: number;
  points: Point[];
  filled: boolean;
}

export interface Pad {
  number: string;
  type: "smd" | "through_hole" | "npth" | "connect";
  shape: string;
  position: Point;
  rotation: number;
  size: Point;
  layers: string[];
  net: string | null;
  drill: { diameter: number; slot_length: number | null; offset: Point | null } | null;
  /** Schema 1.1+ (absent on designs stored with 1.0). */
  id?: string | null;
  uuid?: string | null;
  roundrect_ratio?: number | null;
  clearance?: number | null;
  solder_mask_margin?: number | null;
  solder_paste_margin?: number | null;
  solder_paste_ratio?: number | null;
  zone_connection?: string | null;
}

export interface Footprint {
  reference: string;
  value: string | null;
  footprint: string;
  layer: string;
  side: Side;
  position: Point;
  rotation: number;
  attributes: string[];
  properties: Record<string, string>;
  pads: Pad[];
  graphics: Graphic[];
  uuid: string | null;
  /** Schema 1.1+. */
  id?: string | null;
  locked?: boolean;
}

export interface Track {
  kind: "segment" | "arc";
  start: Point;
  end: Point;
  mid: Point | null;
  width: number;
  layer: string;
  net: string | null;
  length: number;
  /** Schema 1.1+. */
  id?: string | null;
  uuid?: string | null;
  locked?: boolean;
}

export interface ViaDef {
  position: Point;
  diameter: number;
  drill: number;
  layers: string[];
  net: string | null;
  via_type: string;
  /** Schema 1.1+. */
  id?: string | null;
  uuid?: string | null;
  locked?: boolean;
}

export interface Zone {
  net: string | null;
  layers: string[];
  outline: Point[];
  area: number;
  filled: boolean;
  keepout: boolean;
  name: string | null;
  /** Schema 1.1+. */
  id?: string | null;
  uuid?: string | null;
  keepout_rules?: { tracks: boolean | null; vias: boolean | null; pads: boolean | null; copper_pour: boolean | null; footprints: boolean | null } | null;
  priority?: number | null;
  clearance?: number | null;
  min_thickness?: number | null;
}

export interface StackupLayer {
  name: string;
  type: string;
  thickness: number | null;
  material: string | null;
  epsilon_r: number | null;
  loss_tangent: number | null;
}

/** GET /api/v1/pcb/{design_id}/normalized */
export interface PCBDesign {
  schema_version: string;
  engine_version: string;
  source: { format: string; filename: string | null; sha256: string; size_bytes: number; y_axis: string; [k: string]: unknown };
  title: string | null;
  layers: PcbLayerDef[];
  nets: { code: number; name: string }[];
  components: Footprint[];
  tracks: Track[];
  vias: ViaDef[];
  zones: Zone[];
  graphics: Graphic[];
  outline: { graphics: Graphic[]; closed: boolean; bbox: BoundingBox | null; area: number | null };
  bbox: BoundingBox | null;
  stats: DesignStats;
  warnings: ParseWarning[];
  /** Schema 1.1+: null when the source declares no stackup. */
  stackup?: { layers: StackupLayer[]; copper_finish: string | null; dielectric_constraints: boolean | null } | null;
}
