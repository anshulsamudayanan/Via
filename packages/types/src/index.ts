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
