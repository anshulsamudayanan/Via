import type { FeedbackType, LearnCategory, LearnStatus, LearnVerification } from "@via/types";

export const CATEGORY_LABEL: Record<LearnCategory, string> = {
  pcb_design_pattern: "PCB design pattern",
  component_selection: "Component selection",
  routing_practice: "Routing practice",
  thermal_design: "Thermal design",
  signal_integrity: "Signal integrity",
  manufacturing_constraint: "Manufacturing constraint",
  bom_cost_insight: "BOM and cost insight",
  optimization_example: "Optimization example",
  verified_recommendation: "Verified recommendation",
};

export const STATUS_LABEL: Record<LearnStatus, string> = {
  draft: "Draft",
  pending_review: "Pending review",
  approved: "Approved",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
};

export const LEARN_VERIFICATION_LABEL: Record<LearnVerification, string> = {
  unverified: "Unverified",
  reviewed: "Reviewed",
  verified: "Verified",
};

export const FEEDBACK_LABEL: Record<FeedbackType, string> = {
  helpful: "Helpful",
  unhelpful: "Not helpful",
  accepted: "Accepted",
  rejected: "Rejected",
  correction: "Correction",
  incorrect_assumption: "Incorrect assumption",
  comment: "Comment",
};

/** Feedback types that need the user to say why. Mirrors the API. */
export const NEEDS_EXPLANATION = new Set<FeedbackType>(["correction", "incorrect_assumption", "comment", "rejected"]);

export const pct = (v: number | null | undefined) => (v === null || v === undefined ? "n/a" : `${Math.round(v * 100)}%`);
