import { expect, test } from "@playwright/test";

import { chooseFile, currentPath, createProject, REFERENCE_BOARD, register, signIn, signOut, uniqueEmail } from "./helpers";

test("register → create project → upload → view board → select component → sign out → sign in", async ({ page }) => {
  const email = uniqueEmail("core");
  await register(page, "Grace Hopper", email);
  await expect(page.getByRole("heading", { name: /Grace/ })).toBeVisible();

  const projectUrl = await createProject(page, "E2E power board");

  // Edit project information.
  await page.goto(`${projectUrl}?tab=settings`);
  await page.getByLabel("Description").fill("5 V regulator test board");
  await page.getByRole("button", { name: "Save changes" }).click();
  await page.goto(projectUrl);
  await expect(page.getByText("5 V regulator test board")).toBeVisible();

  // Upload the reference board and wait for the worker to parse it.
  await chooseFile(page, projectUrl, REFERENCE_BOARD);
  await expect(page.getByText("4 components", { exact: false })).toBeVisible({ timeout: 60_000 });
  await page.getByRole("link", { name: "Open design" }).click();
  await page.waitForURL("**/designs/**");
  const designUrl = currentPath(page);

  // Design page: real parsed data and the embedded viewer.
  await expect(page.getByRole("img", { name: /Board view of/ })).toBeVisible();
  await expect(page.getByText("Board", { exact: true })).toBeVisible();

  // Extracted components, nets and layers.
  const data = page.getByRole("navigation", { name: "Design data" });
  await data.getByRole("link", { name: "Components" }).click();
  for (const ref of ["R1", "C1", "J1", "H1"]) {
    await expect(page.getByRole("cell", { name: ref, exact: true })).toBeVisible();
  }
  await data.getByRole("link", { name: "Nets" }).click();
  for (const net of ["VCC", "SIG", "GND"]) {
    await expect(page.getByRole("cell", { name: net, exact: true })).toBeVisible();
  }
  await data.getByRole("link", { name: "Layers" }).click();
  await expect(page.getByRole("cell", { name: "F.Cu", exact: true })).toBeVisible();
  await expect(page.getByRole("cell", { name: "B.Cu", exact: true })).toBeVisible();

  // Full-page viewer: find R1 through search and inspect it.
  await page.goto(`${designUrl}/viewer`);
  const canvas = page.getByRole("img", { name: /Board view of/ });
  await expect(canvas).toBeVisible();
  await expect(canvas).toHaveAttribute("aria-label", /4 components/);
  await page.getByRole("tab", { name: "components" }).click();
  await page.getByRole("searchbox", { name: "Search components" }).fill("R1");
  await page.getByRole("button", { name: /^R1\b/ }).first().click();
  const details = page.getByRole("region", { name: "Component R1" });
  await expect(details).toBeVisible();
  await expect(details).toContainText("Pads");

  // Escape clears the selection.
  await page.keyboard.press("Escape");
  await expect(details).toBeHidden();

  // Sign out: protected pages now redirect to the login page.
  await signOut(page);
  await page.goto(projectUrl);
  await expect(page).toHaveURL(/\/login\?next=/);

  // Sign back in: the project and its design are still there.
  await signIn(page, email);
  await page.goto("/projects");
  await page.getByRole("link", { name: "E2E power board" }).click();
  await page.goto(`${projectUrl}?tab=designs`);
  await expect(page.getByRole("link", { name: /via_reference_v8/ }).first()).toBeVisible();
});

test("signed-out visitors are sent to the login page and back after signing in", async ({ page }) => {
  const email = uniqueEmail("redirect");
  await register(page, "Redirect User", email);
  await signOut(page);

  await page.goto("/activity");
  await expect(page).toHaveURL(/\/login\?next=%2Factivity/);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("correct horse battery staple");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/activity");
});
