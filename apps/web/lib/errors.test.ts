import { ApiError } from "@via/api-client";
import { describe, expect, it } from "vitest";

import { rejectedProblems } from "./errors";

describe("rejectedProblems", () => {
  it("returns the grounding problems of a discarded AI answer and nothing for other errors", () => {
    const rejected = new ApiError(502, "ai_output_rejected", "discarded", null, { problems: ["Reference not in the design: net:FOO", 7] });
    expect(rejectedProblems(rejected)).toEqual(["Reference not in the design: net:FOO"]);
    expect(rejectedProblems(new ApiError(503, "ai_unavailable", "x"))).toEqual([]);
    expect(rejectedProblems(new Error("x"))).toEqual([]);
  });
});
