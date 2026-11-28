import { ApiError } from "@via/api-client";

/** User-facing message for any thrown value. */
export function errorMessage(err: unknown, fallback = "Something went wrong. Please try again."): string {
  if (err instanceof ApiError) return err.message;
  return fallback;
}

/** What VIA's grounding check found wrong in a discarded AI answer (`ai_output_rejected`), if anything. */
export function rejectedProblems(err: unknown): string[] {
  if (!(err instanceof ApiError) || err.code !== "ai_output_rejected") return [];
  const problems = (err.details as { problems?: unknown } | undefined)?.problems;
  return Array.isArray(problems) ? problems.filter((p): p is string => typeof p === "string") : [];
}

/**
 * Map a 422 validation error's details to per-field messages.
 * The API reports `{loc: ["body", "email"], message}` entries.
 */
export function fieldErrors(err: unknown): Record<string, string> {
  if (!(err instanceof ApiError) || err.code !== "validation_error" || !Array.isArray(err.details)) return {};
  const out: Record<string, string> = {};
  for (const d of err.details as { loc?: unknown[]; message?: string }[]) {
    const field = d.loc?.[d.loc.length - 1];
    if (typeof field === "string" && d.message && !out[field]) out[field] = d.message.replace(/^Value error, /, "");
  }
  return out;
}

/** Only allow same-site relative redirects (prevents open redirects via ?next=). */
export function safeNext(next: string | null | undefined, fallback = "/dashboard"): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) return fallback;
  return next;
}
