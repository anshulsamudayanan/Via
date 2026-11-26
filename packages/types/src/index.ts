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
  /** Most recent upload in the project (any design), whatever its status. */
  latest_import?: LatestImport | null;
  /** Most recent analysis run in the project (any design). */
  latest_analysis?: LatestAnalysis | null;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface LatestImport {
  design_id: string;
  design_name: string;
  revision_number: number;
  status: RevisionStatus;
  at: string;
}

export interface LatestAnalysis {
  design_id: string;
  design_name: string;
  status: AnalysisStatus;
  at: string;
  /** Only for succeeded runs. */
  finding_count: number | null;
}

export interface ProjectSummary {
  active: number;
  archived: number;
  /** Designs in active projects. */
  designs: number;
  /** Uploads and completed analysis runs in active projects, last 7 days. */
  imports_7d: number;
  analyses_7d: number;
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

export interface RevisionBrief {
  id: string;
  revision_number: number;
  status: RevisionStatus;
  object_counts: Partial<Record<"component_count" | "net_count" | "layer_count" | "copper_layer_count", number>> & Record<string, unknown>;
  created_at: string;
}

/** A design in the cross-project list (GET /designs/browse). */
export interface DesignListItem {
  id: string;
  name: string;
  description: string;
  project: { id: string; name: string };
  my_role: ProjectRole;
  project_archived: boolean;
  revision_count: number;
  created_at: string;
  updated_at: string;
  current_revision: RevisionBrief | null;
  /** Most recent upload, whatever its status. */
  latest_revision: RevisionBrief | null;
  latest_analysis: { status: AnalysisStatus; at: string; revision_number: number; finding_count: number | null } | null;
}

export type DesignSort = "updated" | "created" | "name";
export type DesignStatusFilter = "all" | "ready" | "processing" | "failed";

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
    /** Schema 1.1+: the board inside a project archive, and the other project files used. */
    board_file?: string | null;
    project_files?: string[];
  };
  constraints: DesignConstraintsSummary;
  geometry: BoardGeometry | null;
  stats: DesignStats;
  warnings: ParseWarning[];
}

export interface NetClassInfo {
  name: string;
  clearance: number | null;
  track_width: number | null;
  via_diameter: number | null;
  via_drill: number | null;
  nets: string[];
  patterns?: string[];
}

export interface DesignConstraintsSummary {
  board_thickness?: number | null;
  net_classes?: NetClassInfo[];
  /** Schema 1.1+: "project_file" when the .kicad_pro was imported, else "board_file". */
  rules_source?: "board_file" | "project_file";
  rules?: Record<string, number | boolean | null> | null;
  custom_rules?: { name: string; condition: string | null }[];
  [k: string]: unknown;
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

// --- Stage 2: analysis and findings -------------------------------------------------------

export type Severity = "critical" | "high" | "medium" | "low" | "info";
export type FindingSource = "via_deterministic" | "kicad_drc" | "external_simulation" | "ai_suggestion";
export type FindingVerification = "verified" | "heuristic" | "unverified";
export type FindingStatus = "open" | "reviewed" | "dismissed";
export type AnalysisStatus = "queued" | "running" | "succeeded" | "failed";

export interface CheckInfo {
  id: string;
  version: string;
  category: string;
  title: string;
  description: string;
  source: FindingSource;
}

export interface CheckRun {
  check_id: string;
  version: string;
  status: "ok" | "skipped" | "error";
  finding_count: number;
  duration_ms: number;
  message: string | null;
}

export interface AnalysisRun {
  id: string;
  design_id: string;
  revision_id: string;
  revision_number: number;
  status: AnalysisStatus;
  attempt: number;
  config: { checks?: string[] };
  checks: CheckRun[];
  summary: {
    finding_count?: number;
    by_severity?: Record<Severity, number>;
    checks?: Record<"ok" | "skipped" | "error", number>;
    duration_seconds?: number | null;
  };
  analysis_version: string | null;
  engine_version: string | null;
  design_parser_version: string | null;
  design_schema_version: string | null;
  error_code: string | null;
  error_message: string | null;
  triggered_by: { id: string; display_name: string } | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface FindingObjectRef {
  kind: "component" | "pad" | "track" | "via" | "zone" | "net" | "outline" | "layer";
  id: string;
  label: string | null;
}

export interface Finding {
  id: string;
  run_id: string;
  project_id: string;
  design_id: string;
  revision_id: string;
  check_id: string;
  check_version: string;
  rule: string;
  category: string;
  severity: Severity;
  source: FindingSource;
  verification: FindingVerification;
  confidence: number;
  title: string;
  description: string;
  explanation: string;
  suggested_resolution: string | null;
  objects: FindingObjectRef[];
  components: string[];
  nets: string[];
  region: { bbox: BoundingBox; points: Point[]; layers: string[] } | null;
  fingerprint: string;
  status: FindingStatus;
  status_reason: string | null;
  status_changed_at: string | null;
  inherited: boolean;
  created_at: string;
}

export interface FindingDetail extends Finding {
  evidence: {
    kind: string;
    label: string;
    value: string;
    numeric_value: number | null;
    unit: string | null;
    expected: string | null;
  }[];
  history: {
    from_status: FindingStatus;
    to_status: FindingStatus;
    reason: string | null;
    carried_over: boolean;
    actor: { id: string; display_name: string } | null;
    created_at: string;
  }[];
}

export interface FindingPage {
  items: Finding[];
  total: number;
  limit: number;
  offset: number;
  facets: Record<"severity" | "status" | "category" | "source", Record<string, number>>;
}

export interface FindingFilters {
  severity?: string;
  category?: string;
  source?: string;
  verification?: string;
  status?: string;
  check_id?: string;
  component?: string;
  net?: string;
  q?: string;
  sort?: "severity" | "category" | "title" | "check" | "status" | "confidence";
  order?: "asc" | "desc";
  limit?: number;
  offset?: number;
}

export interface AnalysisComparison {
  base_run: AnalysisRun;
  target_run: AnalysisRun;
  new: Finding[];
  resolved: Finding[];
  persisting: Finding[];
}

// --- Stage 2: VIA Intelligence (AI, always labelled as unverified suggestions) -------------

export interface AIStatus {
  enabled: boolean;
  provider: string;
  text: boolean;
  structured_output: boolean;
  embeddings: boolean;
  external: boolean;
  default_model: string | null;
}

export interface ConsentStatus {
  scope: string;
  granted: boolean;
  policy_version: string;
  granted_at: string | null;
}

export interface AIFocus {
  kind: "finding" | "component" | "net" | "region";
  id: string;
}

export interface AIReference {
  kind: string;
  id: string;
}

export interface AIExplanationOutput {
  answer: string;
  key_points?: string[];
  references?: AIReference[];
  numbers_used?: { value: number; unit?: string | null; source: string }[];
  uncertainties?: string[];
}

export interface AIOutput {
  id: string;
  kind: string;
  source: "ai_suggestion";
  verification: "unverified";
  question: string | null;
  focus: AIFocus | null;
  output: AIExplanationOutput & Record<string, unknown>;
  grounding: { ok: boolean; problems?: string[] } & Record<string, unknown>;
  provider: string;
  model: string;
  prompt_version: string;
  analysis_run_id: string | null;
  revision_id: string;
  created_at: string;
}

export interface Recommendation {
  id: string;
  ai_output_id: string;
  design_id: string;
  revision_id: string;
  source: "ai_suggestion";
  verification: "unverified";
  problem: string;
  proposed_change: string;
  rationale: string;
  expected_benefits: string[];
  trade_offs: string[];
  required_validation: string[];
  uncertainty: string;
  references: AIReference[];
  numbers_used: { value: number; unit?: string | null; source: string }[];
  evidence_finding_ids: string[];
  confidence: string;
  status: "open" | "accepted" | "rejected";
  status_reason: string | null;
  created_at: string;
}

export interface ComponentMatch {
  reference: string;
  value: string | null;
  footprint: string;
  manufacturer: string | null;
  part_number: string | null;
  record_id: string | null;
}

// --- Stage 2: VIA Optimize -----------------------------------------------------------------

export type Objective = "area" | "cost" | "manufacturability" | "routing" | "placement" | "thermal" | "layers";

export interface OptimizationRun {
  id: string;
  design_id: string;
  revision_id: string;
  revision_number: number;
  status: AnalysisStatus;
  attempt: number;
  config: { objectives?: Objective[]; constraints?: Record<string, unknown>; options?: Record<string, unknown> };
  summary: { baseline?: Record<string, number | null>; pareto?: string[]; notes?: string[]; candidate_count?: number; duration_seconds?: number | null };
  optimizer_version: string | null;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  finished_at: string | null;
}

export interface DesignChangeDef {
  id: string;
  ordinal: number;
  kind: string;
  target: { kind: string; id: string; uuid?: string | null; label?: string | null };
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  reason: string;
  source: string;
  exportable: boolean;
}

export type CandidateStatus = "proposed" | "awaiting_validation" | "validated" | "rejected" | "accepted";

export interface CandidateValidation {
  status: "passed" | "failed" | "requires_rerouting" | "manual";
  checks_run: string[];
  new_problems: string[];
  resolved_problems: number;
  constraint_violations: string[];
  notes: string[];
}

export interface Candidate {
  id: string;
  run_id: string;
  key: string;
  algorithm: string;
  algorithm_version: string;
  objectives: string[];
  title: string;
  summary: string;
  metrics_before: Record<string, number | null>;
  metrics_after: Record<string, number | null>;
  expected_benefits: string[];
  trade_offs: string[];
  validation: CandidateValidation;
  pareto: boolean;
  status: CandidateStatus;
  status_reason: string | null;
  change_count: number;
  exportable_changes: number;
}

export interface CandidateDetail extends Candidate {
  changes: DesignChangeDef[];
  details: Record<string, unknown>;
}

export interface OptimizationComparison {
  objectives: string[];
  metrics: string[];
  baseline: Record<string, number | null>;
  rows: { id: string; key: string; title: string; status: string; metrics: Record<string, number | null>; deltas: Record<string, number | null> }[];
  pareto: string[];
  dominance: Record<string, string[]>;
}

// --- Stage 2: change management ------------------------------------------------------------

export type ChangeSetStatus = "draft" | "applying" | "applied" | "failed" | "rolled_back";

export interface ChangeInput {
  kind: string;
  target: { kind: string; id: string; label?: string };
  after: Record<string, number>;
  reason?: string;
}

export interface SetChange {
  id: string;
  ordinal: number;
  kind: string;
  target: { kind: string; id: string; label?: string | null };
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  reason: string;
  source: string;
  origin_candidate_id: string | null;
  status: "proposed" | "applied" | "refused";
  status_reason: string | null;
}

export interface ChangeSet {
  id: string;
  design_id: string;
  base_revision_id: string;
  result_revision_id: string | null;
  export_run_id: string | null;
  title: string;
  status: ChangeSetStatus;
  result: { applied?: number; sha256?: string; size_bytes?: number; verification?: string; follow_up_analysis_run_id?: string } & Record<string, unknown>;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  applied_at: string | null;
  rolled_back_at: string | null;
  changes: SetChange[];
}

export interface ChangePreview {
  source: "simulated";
  before: Record<string, number | null>;
  after: Record<string, number | null>;
  deltas: Record<string, number | null>;
}

export interface LineageEntry {
  revision_id: string;
  revision_number: number;
  status: RevisionStatus;
  parent_revision_id: string | null;
  change_set_id: string | null;
  created_at: string;
}

export interface FindingBrief {
  id: string;
  rule: string;
  severity: Severity;
  title: string;
  source: FindingSource;
}

export interface RevisionComparison {
  base: { revision_id: string; revision_number: number; analysis_run_id: string | null };
  head: { revision_id: string; revision_number: number; analysis_run_id: string | null };
  object_counts: Record<string, { base: number | null; head: number | null }>;
  findings: { introduced: FindingBrief[]; resolved: FindingBrief[]; persisting: number; base_total: number; head_total: number } | null;
  findings_note?: string;
}

// --- Cross-project views (sidebar Analysis and Components pages) ---------------------------

export interface NamedRef {
  id: string;
  name: string;
}

export interface RunListItem {
  id: string;
  status: AnalysisStatus;
  design: NamedRef;
  project: NamedRef;
  project_archived: boolean;
  revision_id: string;
  revision_number: number;
  /** Only for succeeded runs. */
  finding_count: number | null;
  by_severity: Partial<Record<Severity, number>>;
  error_code: string | null;
  triggered_by: UserRef | null;
  created_at: string;
  finished_at: string | null;
}

export interface FindingListItem {
  id: string;
  run_id: string;
  design: NamedRef;
  project: NamedRef;
  revision_id: string;
  revision_number: number;
  check_id: string;
  rule: string;
  category: string;
  severity: Severity;
  source: FindingSource;
  verification: FindingVerification;
  title: string;
  status: FindingStatus;
  components: string[];
  nets: string[];
  created_at: string;
}

export interface FindingListPage extends Page<FindingListItem> {
  /** Counts per severity over the same filters, ignoring the severity filter. */
  by_severity: Partial<Record<Severity, number>>;
  /** Designs with a succeeded analysis in scope. */
  designs_analysed: number;
}

export type PartSort = "placements" | "value" | "footprint";

export interface PartListItem {
  value: string | null;
  footprint: string;
  placements: number;
  design_count: number;
  /** Up to 12, natural order. */
  references: string[];
  references_truncated: boolean;
  /** Up to 5. */
  designs: { id: string; name: string; project_id: string }[];
}

export interface PartListPage extends Page<PartListItem> {
  placements: number;
  designs: number;
}
