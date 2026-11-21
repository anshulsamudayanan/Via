import { ApiError } from "@via/api-client";
import type { ActivityItem } from "@via/types";
import { describe, expect, it } from "vitest";

import { describeActivity } from "./activity";
import { fieldErrors, safeNext } from "./errors";
import { relativeTime } from "./format";

describe("safeNext", () => {
  it.each([
    ["/projects/1", "/projects/1"],
    [null, "/dashboard"],
    ["https://evil.example", "/dashboard"],
    ["//evil.example", "/dashboard"],
    ["/\\evil.example", "/dashboard"],
    ["javascript:alert(1)", "/dashboard"],
  ])("%s -> %s", (input, expected) => {
    expect(safeNext(input)).toBe(expected);
  });
});

describe("fieldErrors", () => {
  it("maps validation details to fields", () => {
    const err = new ApiError(422, "validation_error", "Request validation failed", null, [
      { loc: ["body", "email"], message: "Value error, Enter a valid email address.", type: "value_error" },
    ]);
    expect(fieldErrors(err)).toEqual({ email: "Enter a valid email address." });
    expect(fieldErrors(new Error("x"))).toEqual({});
  });
});

describe("relativeTime", () => {
  const now = new Date("2026-11-21T12:00:00Z");
  it("formats past times", () => {
    expect(relativeTime("2026-11-21T11:59:30Z", now)).toBe("just now");
    expect(relativeTime("2026-11-21T11:55:00Z", now)).toBe("5 minutes ago");
    expect(relativeTime("2026-11-20T12:00:00Z", now)).toBe("yesterday");
  });
});

describe("describeActivity", () => {
  const item = (action: string, details: Record<string, unknown> = {}): ActivityItem => ({
    id: "a", action, details, created_at: "", actor: null, project: null, target_type: null, target_id: null,
  });
  it("describes known actions from real details", () => {
    expect(describeActivity(item("project.updated", { changes: { name: { from: "A", to: "B" }, description: true } }))).toBe(
      'renamed it to "B", edited the description',
    );
    expect(describeActivity(item("project.member_added", { member: "Bob", role: "editor" }))).toBe("added Bob as editor");
    expect(describeActivity(item("project.member_removed", { self: true }))).toBe("left the project");
  });
  it("falls back to the raw action name", () => {
    expect(describeActivity(item("something.new"))).toBe("something.new");
  });
});
