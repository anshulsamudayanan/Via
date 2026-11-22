import { expect, test } from "@playwright/test";

import { chooseFile, currentPath, idAfter, createProject, REFERENCE_BOARD, register, uniqueEmail } from "./helpers";

test("another user can't see a private project, its designs or its files", async ({ browser }) => {
  const owner = await browser.newPage();
  await register(owner, "Owner", uniqueEmail("owner"));
  const projectUrl = await createProject(owner, "Private board");
  await chooseFile(owner, projectUrl, REFERENCE_BOARD);
  await owner.getByRole("link", { name: "Open design" }).click({ timeout: 60_000 });
  await owner.waitForURL("**/designs/**");
  const designUrl = currentPath(owner);
  const projectId = idAfter(projectUrl, "projects");
  const designId = idAfter(designUrl, "designs");

  const strangerContext = await browser.newContext();
  const stranger = await strangerContext.newPage();
  await register(stranger, "Stranger", uniqueEmail("stranger"));

  // Not listed anywhere.
  await stranger.goto("/projects");
  await expect(stranger.getByText("Private board")).toHaveCount(0);

  // Direct links show "not found", exactly like a project that doesn't exist.
  await stranger.goto(projectUrl);
  await expect(stranger.getByText("Project not found")).toBeVisible();
  await stranger.goto(designUrl);
  await expect(stranger.getByText(/not found/i).first()).toBeVisible();
  await stranger.goto(`${designUrl}/viewer`);
  await expect(stranger.getByText(/not found/i).first()).toBeVisible();

  // Every read endpoint works for the owner and answers 404 to the stranger, with the stranger's real session.
  const [firstFile] = (await (await owner.request.get(`/api/v1/files?project_id=${projectId}`)).json()) as { id: string }[];
  if (!firstFile) throw new Error("The owner should see the uploaded source file");
  const paths = [
    `/api/v1/projects/${projectId}`,
    `/api/v1/projects/${projectId}/members`,
    `/api/v1/designs?project_id=${projectId}`,
    `/api/v1/files?project_id=${projectId}`,
    `/api/v1/files/${firstFile.id}/download`,
    `/api/v1/designs/${designId}`,
    `/api/v1/pcb/${designId}`,
    `/api/v1/pcb/${designId}/normalized`,
    `/api/v1/pcb/${designId}/components`,
    `/api/v1/pcb/${designId}/nets`,
    `/api/v1/pcb/${designId}/layers`,
    `/api/v1/ai/consent/${projectId}`,
  ];
  for (const path of paths) {
    expect((await owner.request.get(path)).status(), `owner ${path}`).toBe(200);
    expect((await stranger.request.get(path)).status(), `stranger ${path}`).toBe(404);
  }

  // Writes are refused the same way.
  const rename = await stranger.request.patch(`/api/v1/projects/${projectId}`, {
    data: { name: "pwned" },
    headers: { "X-VIA-Request": "1" },
  });
  expect(rename.status()).toBe(404);

  await strangerContext.close();
});
