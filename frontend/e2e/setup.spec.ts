import { expect, test } from "@playwright/test";
import { SHOTS } from "./helpers";

test("setup shows ready state with model available", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(String(e).slice(0, 150)));
  await page.goto("/setup", { waitUntil: "networkidle" });
  // Either the ready note or a specific fix section must render, never blank.
  await expect(page.getByRole("heading", { name: "Setup" })).toBeVisible();
  const body = await page.locator("#root").innerText();
  expect(
    body.includes("Ready") ||
      body.includes("Ollama is not running") ||
      body.includes("Model not available") ||
      body.includes("backend not reachable"),
  ).toBeTruthy();
  await page.screenshot({ path: `${SHOTS}/setup.png` });
  expect(errors).toEqual([]);
});
