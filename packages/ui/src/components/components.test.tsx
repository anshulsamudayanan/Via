import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Badge, Button, EmptyState, ErrorState, Spinner } from "../index";

afterEach(cleanup);

describe("design system", () => {
  it("Button defaults to type=button so it never submits forms by accident", () => {
    render(<Button>Save</Button>);
    expect(screen.getByRole("button", { name: "Save" }).getAttribute("type")).toBe("button");
  });

  it("Button asChild renders the child element with button styles", () => {
    render(
      <Button asChild variant="primary">
        <a href="/x">Go</a>
      </Button>,
    );
    const link = screen.getByRole("link", { name: "Go" });
    expect(link.className).toContain("bg-accent");
    expect(link.getAttribute("type")).toBeNull();
  });

  it("ErrorState is announced as an alert", () => {
    render(<ErrorState title="Upload failed" description="File too large" />);
    expect(screen.getByRole("alert").textContent).toContain("Upload failed");
  });

  it("Spinner exposes an accessible status label", () => {
    render(<Spinner label="Loading projects" />);
    expect(screen.getByRole("status").textContent).toContain("Loading projects");
  });

  it("EmptyState renders title, description and action", () => {
    render(<EmptyState title="No projects" description="Create one" action={<Button>New</Button>} />);
    expect(screen.getByText("No projects")).toBeTruthy();
    expect(screen.getByRole("button", { name: "New" })).toBeTruthy();
  });

  it("Badge tones map to semantic tokens", () => {
    render(<Badge tone="danger">Failed</Badge>);
    expect(screen.getByText("Failed").className).toContain("text-danger");
  });
});
