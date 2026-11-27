import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Badge, Button, CountUp, EmptyState, ErrorState, Spinner } from "../index";

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

describe("forms and overlays", () => {
  it("Field wires label, error and aria attributes to the control", async () => {
    const { Field, Input } = await import("../index");
    render(<Field label="Email" error="Enter a valid email address.">{(p) => <Input {...p} />}</Field>);
    const input = screen.getByLabelText("Email");
    expect(input.getAttribute("aria-invalid")).toBe("true");
    const describedBy = input.getAttribute("aria-describedby")!;
    expect(document.getElementById(describedBy)?.textContent).toBe("Enter a valid email address.");
  });

  it("Dialog is labelled by its title and closes on Escape", async () => {
    const { default: userEvent } = await import("@testing-library/user-event");
    const { Dialog, DialogContent, DialogTrigger } = await import("../index");
    const user = userEvent.setup();
    render(
      <Dialog>
        <DialogTrigger asChild>
          <Button>Open</Button>
        </DialogTrigger>
        <DialogContent title="New project" description="Create a project">
          <p>Body</p>
        </DialogContent>
      </Dialog>,
    );
    await user.click(screen.getByRole("button", { name: "Open" }));
    const dialog = screen.getByRole("dialog", { name: "New project" });
    expect(dialog.textContent).toContain("Body");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("CountUp shows the real value on first render, never a false zero", () => {
    render(<CountUp value={3} />);
    expect(screen.getByText("3")).toBeTruthy();
    expect(screen.queryByText("0")).toBeNull();
  });

  it("CountUp settles on the new value when it changes, passing only between real values", async () => {
    const { container, rerender } = render(<CountUp value={3} />);
    rerender(<CountUp value={7} />);
    const seen = Number(container.textContent);
    expect(seen).toBeGreaterThanOrEqual(3);
    expect(seen).toBeLessThanOrEqual(7);
    await waitFor(() => expect(container.textContent).toBe("7"));
  });
});
