import type { PCBDesign } from "@via/types";
import { fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import board from "@/test/fixtures/reference-board.json";
import { mockClient, renderWith } from "@/test/helpers";

import { BoardViewer } from "./board-viewer";

const design = board as unknown as PCBDesign;

function setup() {
  const normalized = vi.fn().mockResolvedValue(design);
  renderWith(<BoardViewer designId="d1" designName="Reference" expandHref="/x/viewer" className="h-96" />, mockClient({ pcb: { normalized } }));
  return normalized;
}

describe("BoardViewer", () => {
  it("loads the parsed design and describes it accessibly", async () => {
    const normalized = setup();
    const canvas = await screen.findByRole("img", { name: /Board view of Reference: 4 components, 2 copper layers, 8 tracks, 1 vias/ });
    expect(canvas.getAttribute("tabindex")).toBe("0");
    expect(normalized).toHaveBeenCalledWith("d1", undefined, expect.anything());
    expect(screen.getByRole("link", { name: "Open full-page viewer" }).getAttribute("href")).toBe("/x/viewer");
  });

  it("lists layers with sensible default visibility and toggles them", async () => {
    setup();
    const fcu = (await screen.findByRole("checkbox", { name: "F.Cu" })) as HTMLInputElement;
    expect(fcu.checked).toBe(true);
    expect((screen.getByRole("checkbox", { name: "F.CrtYd" }) as HTMLInputElement).checked).toBe(false);
    expect((screen.getByRole("checkbox", { name: "Edge.Cuts" }) as HTMLInputElement).checked).toBe(true);
    await userEvent.click(fcu);
    expect(fcu.checked).toBe(false);
    expect(screen.getByRole("checkbox", { name: "Vias (1)" })).toBeTruthy();
  });

  it("searches components and shows the selection's properties and pad nets", async () => {
    setup();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("tab", { name: "components" }));
    await user.type(screen.getByRole("searchbox", { name: "Search components" }), "10k");
    const list = screen.getByRole("list");
    expect(within(list).getAllByRole("button")).toHaveLength(1);
    await user.click(within(list).getByRole("button", { name: /R1/ }));
    const panel = screen.getByRole("region", { name: "Component R1" });
    expect(within(panel).getByText("Resistor_SMD:R_0603_1608Metric")).toBeTruthy();
    expect(within(panel).getByText("110.000, 110.000 mm")).toBeTruthy();
    expect(within(panel).getByText("VCC")).toBeTruthy();
    expect(within(panel).getByText("SIG")).toBeTruthy();
    fireEvent.keyDown(screen.getByRole("img"), { key: "Escape" });
    expect(screen.queryByRole("region", { name: "Component R1" })).toBeNull();
  });

  it("shows an error if the board can't be loaded", async () => {
    const { ApiError } = await import("@via/api-client");
    const normalized = vi.fn().mockRejectedValue(new ApiError(409, "not_parsed", "This design has no successfully parsed revision yet."));
    renderWith(<BoardViewer designId="d1" designName="X" />, mockClient({ pcb: { normalized } }));
    expect((await screen.findByRole("alert")).textContent).toContain("no successfully parsed revision");
  });
});
