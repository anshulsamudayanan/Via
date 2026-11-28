import type { Evaluation, FeedbackItem, LearnEntry, Recommendation } from "@via/types";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { me, mockClient, navigation, page, renderWith, router } from "@/test/helpers";

import { LearnBrowser } from "./learn-browser";
import { RecommendationFeedback } from "./recommendation-feedback";

const entry = (o: Partial<LearnEntry> = {}): LearnEntry => ({
  id: "e1", category: "thermal_design", title: "Copper pour under a regulator", description: "Use a pour under the thermal pad.",
  technical_metadata: {}, source: "Datasheet", provenance: {}, origin: "free_text", status: "approved", verification_status: "unverified",
  verification_basis: null, version: 1, mine: false, score: 0.5, permissions: null, review_note: null, submitted_at: null,
  reviewed_at: null, withdrawn_at: null, created_at: "2026-11-27T10:00:00Z", updated_at: "2026-11-27T10:00:00Z", ...o,
});

const rec: Recommendation = {
  id: "rec1", output_id: "o1", design_id: "d1", revision_id: "r1", problem: "Thin trace", proposed_change: "Widen it", rationale: "Current",
  confidence: "medium", required_validation: [], evidence_finding_ids: [], status: "open", status_reason: null, created_at: "2026-11-27T10:00:00Z",
  knowledge: [{ entry_id: "e1", version: 1, title: "Copper pour", category: "thermal_design", verification_status: "unverified", source: "Datasheet", status: "approved", cited: true }],
} as unknown as Recommendation;

beforeEach(() => {
  navigation.pathname = "/learn";
  navigation.search = new URLSearchParams();
  router.replace.mockReset();
});

describe("Library", () => {
  it("shows approved entries with verification and source, and says retrieval is keyword-based", async () => {
    const meta = { categories: ["thermal_design"], verification_levels: [], is_reviewer: false, policy_version: "v", retrieval: { method: "postgres_full_text", semantic: false, note: "Keyword search, not semantic." } };
    renderWith(<LearnBrowser />, mockClient({ learn: { meta: vi.fn().mockResolvedValue(meta), search: vi.fn().mockResolvedValue(page([entry()])) } }));
    expect(await screen.findByText("Copper pour under a regulator")).toBeTruthy();
    expect(screen.getAllByText("Unverified").some((el) => el.tagName !== "OPTION")).toBe(true);
    expect(screen.getByText(/Source: Datasheet/)).toBeTruthy();
    expect(await screen.findByText("Keyword search, not semantic.")).toBeTruthy();
  });

  it("hides the review tab from ordinary users", async () => {
    renderWith(<LearnBrowser />, mockClient());
    expect(await screen.findByText("The library is empty")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Contribution review" })).toBeNull();
  });

  it("shows the review tab to reviewers", async () => {
    const reviewer = { ...me, user: { ...me.user, learn_reviewer: true } };
    renderWith(<LearnBrowser />, mockClient(), { me: reviewer });
    expect(await screen.findByRole("button", { name: "Contribution review" })).toBeTruthy();
  });
});

describe("Linked entry", () => {
  it("opens the entry a recommendation cited, and says so when it is gone", async () => {
    navigation.search = new URLSearchParams("entry=e9");
    const found = vi.fn().mockResolvedValue(entry({ id: "e9", title: "Cited note" }));
    const { unmount } = renderWith(<LearnBrowser />, mockClient({ learn: { entry: found } }));
    expect(await screen.findByText("Cited note")).toBeTruthy();
    expect(found).toHaveBeenCalledWith("e9", expect.anything());
    unmount();
    renderWith(<LearnBrowser />, mockClient({ learn: { entry: vi.fn().mockRejectedValue(new Error("nope")) } }));
    expect(await screen.findByText(/no longer available/)).toBeTruthy();
  });
});

describe("My contributions", () => {
  it("needs the rights confirmation before a draft can be saved, then creates it", async () => {
    navigation.search = new URLSearchParams("view=contributions");
    const contribute = vi.fn().mockResolvedValue(entry({ status: "draft", mine: true }));
    renderWith(<LearnBrowser />, mockClient({ learn: { contribute }, projects: { list: vi.fn().mockResolvedValue(page([])) } }));
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Title"), "Keep pours solid");
    await user.type(screen.getByLabelText("Description"), "A solid pour carries heat better than hatching.");
    await user.type(screen.getByLabelText("Source"), "Experience");
    expect((screen.getByRole("button", { name: "Save draft" }) as HTMLButtonElement).disabled).toBe(true);
    await user.click(screen.getByRole("checkbox", { name: /mine to share/ }));
    await user.click(screen.getByRole("button", { name: "Save draft" }));
    await waitFor(() => expect(contribute).toHaveBeenCalledWith(expect.objectContaining({ title: "Keep pours solid", confirm_rights: true })));
  });

  it("lets the contributor submit a draft and withdraw an approved entry", async () => {
    navigation.search = new URLSearchParams("view=contributions");
    const submit = vi.fn().mockResolvedValue(entry());
    const withdraw = vi.fn().mockResolvedValue(entry({ status: "withdrawn" }));
    const contributions = vi.fn().mockResolvedValue(page([
      entry({ id: "d1", status: "draft", mine: true, title: "A draft" }),
      entry({ id: "a1", status: "approved", mine: true, title: "An approved one", permissions: { library_visible: true, ai_retrieval: true } }),
    ]));
    renderWith(<LearnBrowser />, mockClient({ learn: { contributions, submit, withdraw }, projects: { list: vi.fn().mockResolvedValue(page([])) } }));
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Submit for review" }));
    expect(submit).toHaveBeenCalledWith("d1");
    await user.click(screen.getByRole("button", { name: "Withdraw" }));
    expect(withdraw).toHaveBeenCalledWith("a1");
  });

  it("shows a withdrawn entry as erased", async () => {
    navigation.search = new URLSearchParams("view=contributions");
    const contributions = vi.fn().mockResolvedValue(page([entry({ status: "withdrawn", mine: true, title: "", description: "", withdrawn_at: "2026-11-28T10:00:00Z" })]));
    renderWith(<LearnBrowser />, mockClient({ learn: { contributions }, projects: { list: vi.fn().mockResolvedValue(page([])) } }));
    expect(await screen.findByText("Withdrawn by contributor")).toBeTruthy();
    expect(screen.getByText(/content was erased/)).toBeTruthy();
  });
});

describe("Insights", () => {
  it("labels what cannot be measured", async () => {
    navigation.search = new URLSearchParams("view=insights");
    const tally = { recommendations: 2, accepted: 1, rejected: 1, acceptance_rate: 0.5, rejection_rate: 0.5, helpful: 0, unhelpful: 0, helpful_rate: null, corrections: 0, incorrect_assumptions: 0, evidence_resolved: 0, evidence_persisting: 0, evidence_not_checkable: 2, evidence_resolution_rate: null };
    const evaluation: Evaluation = {
      scope: "projects", projects: 1, capped: false, summary: tally, grounding: { reviews: 2, rejected: 0, rejection_rate: 0 },
      by_category: [{ category: "thermal", ...tally }], by_version: [], by_board_bucket: [],
      not_measurable: [{ metric: "false positive and false negative rates", reason: "No ground truth." }], notes: ["Acceptance is a decision."],
    };
    renderWith(<LearnBrowser />, mockClient({ learn: { evaluation: vi.fn().mockResolvedValue(evaluation) } }));
    expect(await screen.findByText(/Not measurable: false positive and false negative rates/)).toBeTruthy();
    expect(screen.getByText("thermal")).toBeTruthy();
    expect(screen.getAllByText("50%").length).toBeGreaterThan(0);
  });
});

describe("Feedback history", () => {
  it("lists the user's own feedback with model versions", async () => {
    navigation.search = new URLSearchParams("view=feedback");
    const item: FeedbackItem = {
      id: "f1", recommendation_id: "rec1", project_id: "p1", design_id: "d1", analysis_run_id: null, category: "power", feedback_type: "correction",
      explanation: "Wrong rail", model: "m1", prompt_version: "p1", engine_version: "0.3", by: "Ada", mine: true, created_at: "2026-11-27T10:00:00Z",
    };
    renderWith(<LearnBrowser />, mockClient({ learn: { feedbackHistory: vi.fn().mockResolvedValue(page([item])) } }));
    expect(await screen.findByText("Wrong rail")).toBeTruthy();
    expect(screen.getByText(/m1 · prompt p1/)).toBeTruthy();
  });
});

describe("RecommendationFeedback", () => {
  it("sends one-click feedback, and requires an explanation for a correction", async () => {
    const feedback = vi.fn().mockResolvedValue({});
    renderWith(<RecommendationFeedback rec={rec} canEdit isOwner={false} />, mockClient({ learn: { feedback } }));
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Helpful" }));
    expect(feedback).toHaveBeenCalledWith("rec1", { feedback_type: "helpful", explanation: undefined });
    await user.click(screen.getByRole("button", { name: "Correction" }));
    expect((screen.getByRole("button", { name: "Send correction" }) as HTMLButtonElement).disabled).toBe(true);
    await user.type(screen.getByLabelText("Correction details"), "It is the 5V rail");
    await user.click(screen.getByRole("button", { name: "Send correction" }));
    expect(feedback).toHaveBeenLastCalledWith("rec1", { feedback_type: "correction", explanation: "It is the 5V rail" });
  });

  it("shows which library notes the model saw and whether it cited them", () => {
    renderWith(<RecommendationFeedback rec={rec} canEdit={false} isOwner={false} />, mockClient());
    expect(screen.getByText("Copper pour")).toBeTruthy();
    expect(screen.getByText("cited")).toBeTruthy();
  });

  it("offers contribution only to project owners", async () => {
    const contributeRecommendation = vi.fn().mockResolvedValue(entry({ status: "draft" }));
    const { unmount } = renderWith(<RecommendationFeedback rec={rec} canEdit isOwner={false} />, mockClient());
    expect(screen.queryByRole("button", { name: "Contribute to VIA Learn" })).toBeNull();
    unmount();
    renderWith(<RecommendationFeedback rec={rec} canEdit isOwner />, mockClient({ learn: { contributeRecommendation } }));
    await userEvent.setup().click(screen.getByRole("button", { name: "Contribute to VIA Learn" }));
    expect(contributeRecommendation).toHaveBeenCalledWith("rec1");
    expect(await screen.findByText(/Draft created/)).toBeTruthy();
  });

  it("shows the API's reason when consent is missing", async () => {
    const { ApiError } = await import("@via/api-client");
    const contributeRecommendation = vi.fn().mockRejectedValue(new ApiError(403, "consent_required", "The project owner has not allowed contributions to VIA Learn."));
    renderWith(<RecommendationFeedback rec={rec} canEdit isOwner />, mockClient({ learn: { contributeRecommendation } }));
    await userEvent.setup().click(screen.getByRole("button", { name: "Contribute to VIA Learn" }));
    expect((await screen.findByRole("alert")).textContent).toMatch(/not allowed contributions/);
  });
});
