import { ApiError } from "@via/api-client";
import type { BoardSummary } from "@via/types";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { design, mockClient, navigation, page, project, renderWith, revision } from "@/test/helpers";

import { DesignView, designRulesLabel } from "./design-view";
import { DesignsSection } from "./project-sections";
import { UploadPanel, validateFile } from "./upload-panel";

const limits = { max_upload_bytes: 1024, formats: [{ id: "kicad", name: "KiCad PCB", extensions: [".kicad_pcb"] }] };
const file = (name: string, size: number) => new File(["x".repeat(size)], name);

describe("validateFile", () => {
  it("checks extension, emptiness and size like the API", () => {
    expect(validateFile(file("board.kicad_pcb", 10), limits)).toBeNull();
    expect(validateFile(file("BOARD.KICAD_PCB", 10), limits)).toBeNull();
    expect(validateFile(file("board.brd", 10), limits)).toMatch(/Unsupported file type/);
    expect(validateFile(file("board.kicad_pcb", 0), limits)).toBe("The file is empty.");
    expect(validateFile(file("board.kicad_pcb", 2048), limits)).toMatch(/limit is 1.0 KB/);
  });
});

describe("project archives", () => {
  it("accepts a .zip when the API lists KiCad projects", () => {
    const withZip = { ...limits, formats: [...limits.formats, { id: "kicad_project", name: "KiCad project (.zip)", extensions: [".zip"] }] };
    expect(validateFile(file("video.zip", 10), withZip)).toBeNull();
    expect(validateFile(file("video.zip", 10), limits)).toMatch(/Unsupported file type/);
  });

  it("labels where the design rules came from", () => {
    const base = { constraints: {} } as unknown as BoardSummary;
    expect(designRulesLabel(base)).toBe("Board file only (upload the project .zip for its rules)");
    const fromProject = {
      constraints: { rules_source: "project_file", net_classes: [{ name: "Default" }, { name: "pwr" }], custom_rules: [{ name: "hv" }] },
    } as unknown as BoardSummary;
    expect(designRulesLabel(fromProject)).toBe("Project file · 2 net classes · 1 custom rule");
  });
});

describe("UploadPanel", () => {
  it("uploads with progress, then follows parsing to the result", async () => {
    const pending = revision({ status: "pending", object_counts: {} });
    const upload = vi.fn().mockImplementation(async ({ onProgress }) => {
      onProgress(5, 10);
      return { design: design(), revision: pending };
    });
    const get = vi.fn().mockResolvedValue(revision());
    renderWith(<UploadPanel projectId="p1" />, mockClient({ pcb: { upload }, revisions: { get } }));
    const user = userEvent.setup();
    await screen.findByText(/up to 1.0 KB/);
    await user.upload(screen.getByLabelText("Choose a PCB file"), file("board.kicad_pcb", 10));
    expect(upload).toHaveBeenCalledWith(expect.objectContaining({ projectId: "p1" }));
    expect(await screen.findByText("Queued")).toBeTruthy();
    expect(await screen.findByText("Parsed", {}, { timeout: 3000 })).toBeTruthy();
    expect(screen.getByText(/4 components, 3 nets, 18 layers/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Open design" }).getAttribute("href")).toBe("/projects/p1/designs/d1");
  });

  it("rejects unsupported files without uploading", async () => {
    const upload = vi.fn();
    renderWith(<UploadPanel projectId="p1" />, mockClient({ pcb: { upload } }));
    const user = userEvent.setup({ applyAccept: false });
    await screen.findByText(/up to 1.0 KB/);
    await user.upload(screen.getByLabelText("Choose a PCB file"), file("board.zip", 10));
    expect((await screen.findByRole("alert")).textContent).toContain("Unsupported file type");
    expect(upload).not.toHaveBeenCalled();
  });

  it("links to the existing design on duplicates", async () => {
    const upload = vi.fn().mockRejectedValue(
      new ApiError(409, "duplicate_file", 'This exact file is already in the project as "Motor board" revision 1.', null, { design_id: "d9", design_name: "Motor board" }),
    );
    renderWith(<UploadPanel projectId="p1" />, mockClient({ pcb: { upload } }));
    const user = userEvent.setup();
    await screen.findByText(/up to 1.0 KB/);
    await user.upload(screen.getByLabelText("Choose a PCB file"), file("board.kicad_pcb", 10));
    expect((await screen.findByRole("alert")).textContent).toContain("already in the project");
    expect(screen.getByRole("link", { name: "Open Motor board" }).getAttribute("href")).toBe("/projects/p1/designs/d9");
  });

  it("shows parse failures with the reason and reports that parsing settled", async () => {
    const failed = revision({ status: "failed", error_code: "invalid_file", error_message: "Malformed KiCad file (line 3)", object_counts: {} });
    const upload = vi.fn().mockResolvedValue({ design: design(), revision: failed });
    const onSettled = vi.fn();
    renderWith(<UploadPanel projectId="p1" onSettled={onSettled} />, mockClient({ pcb: { upload } }));
    const user = userEvent.setup();
    await screen.findByText(/up to 1.0 KB/);
    await user.upload(screen.getByLabelText("Choose a PCB file"), file("board.kicad_pcb", 10));
    expect((await screen.findByRole("alert")).textContent).toContain("Malformed KiCad file (line 3) (invalid_file)");
    await waitFor(() => expect(onSettled).toHaveBeenCalledWith(expect.objectContaining({ status: "failed" })));
  });
});

describe("DesignsSection", () => {
  it("lists designs with parse status and counts; viewers get no upload panel", async () => {
    const list = vi.fn().mockResolvedValue([design()]);
    renderWith(<DesignsSection project={project({ my_role: "viewer" })} />, mockClient({ designs: { list } }));
    expect(await screen.findByRole("link", { name: "Motor board" })).toBeTruthy();
    expect(screen.getByText("Parsed")).toBeTruthy();
    expect(screen.queryByLabelText("Choose a PCB file")).toBeNull();
  });
});

describe("DesignView", () => {
  const summary: BoardSummary = {
    design: { id: "d1", name: "Motor board", project_id: "p1" },
    revision: revision(),
    title: "VIA Reference Board",
    source: { format: "kicad", format_version: "20240108", generator: "pcbnew", generator_version: "8.0", filename: "board.kicad_pcb", size_bytes: 512 },
    constraints: {},
    geometry: { outline_closed: true, min_x: 100, min_y: 100, max_x: 150, max_y: 130, width: 50, height: 30, area: 1500, thickness: 1.6, copper_layer_count: 2 },
    stats: {
      layer_count: 18, copper_layer_count: 2, net_count: 3, component_count: 4, pad_count: 7, smd_pad_count: 4, through_hole_pad_count: 2,
      track_count: 8, via_count: 1, zone_count: 1, total_track_length: 75.745, board_width: 50, board_height: 30, board_area: 1500,
      board_thickness: 1.6, min_track_width: 0.25, min_via_drill: 0.3, min_via_diameter: 0.6, components_top: 3, components_bottom: 1, unconnected_pad_count: 0,
    },
    warnings: [{ code: "unsupported_curve", message: "Bezier curve on layer F.SilkS is not supported and was skipped" }],
  };

  it("shows board information, warnings and components from the API", async () => {
    navigation.pathname = "/projects/p1/designs/d1";
    const client = mockClient({
      projects: { get: vi.fn().mockResolvedValue(project()) },
      designs: { get: vi.fn().mockResolvedValue(design()) },
      pcb: {
        summary: vi.fn().mockResolvedValue(summary),
        components: vi.fn().mockResolvedValue(page([{ id: "c1", reference: "R1", value: "10k", footprint: "R_0603", layer: "F.Cu", side: "top", x: 110, y: 110, rotation: 0, pad_count: 2, attributes: ["smd"], properties: {} }])),
      },
    });
    renderWith(<DesignView />, client);
    expect(await screen.findByRole("heading", { name: "Motor board" })).toBeTruthy();
    expect(await screen.findByText("50 × 30 mm")).toBeTruthy();
    expect(screen.getByText("1500 mm²")).toBeTruthy();
    expect(screen.getByText("Parser warnings (1)")).toBeTruthy();
    expect(screen.getByText("unsupported_curve")).toBeTruthy();
    // The board viewer loads this design's parsed data (rendering is covered in viewer tests).
    await waitFor(() => expect(client.pcb.normalized).toHaveBeenCalledWith("d1", undefined, expect.anything()));
    expect(await screen.findByText("R1")).toBeTruthy();
    await waitFor(() => expect(client.pcb.components).toHaveBeenCalledWith("d1", expect.objectContaining({ limit: 50, offset: 0 }), expect.anything()));
  });

  it("explains when nothing has been parsed", async () => {
    const failed = revision({ status: "failed", error_code: "invalid_file", error_message: "Malformed", object_counts: {} });
    const client = mockClient({
      projects: { get: vi.fn().mockResolvedValue(project()) },
      designs: { get: vi.fn().mockResolvedValue(design({ current_revision: null, latest_revision: failed, revisions: [failed] })) },
    });
    renderWith(<DesignView />, client);
    expect(await screen.findByText("Revision 1 failed to parse")).toBeTruthy();
    expect(screen.getByText("No parsed revision yet")).toBeTruthy();
    expect(client.pcb.summary).not.toHaveBeenCalled();
  });
});

describe("UploadPanel before limits load", () => {
  it("doesn't drop a file chosen before the limits arrive", async () => {
    let resolveLimits: (v: typeof limits) => void = () => {};
    const limitsCall = vi.fn().mockImplementation(() => new Promise((r) => (resolveLimits = r)));
    const upload = vi.fn().mockResolvedValue({ design: design(), revision: revision() });
    renderWith(<UploadPanel projectId="p1" />, mockClient({ pcb: { limits: limitsCall, upload } }));
    const user = userEvent.setup();
    await user.upload(screen.getByLabelText("Choose a PCB file"), file("board.kicad_pcb", 10));
    resolveLimits(limits);
    await waitFor(() => expect(upload).toHaveBeenCalled());
  });
});
