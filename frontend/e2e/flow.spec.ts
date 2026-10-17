import fs from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";
import { SHOTS, deleteByName, uploadAndWait } from "./helpers";

const DIRTY = fs.readFileSync(
  path.join(import.meta.dirname, "../../backend/tests/fixtures/harbor-supply-pricing.xlsx"),
);

test.describe("workbook flow", () => {
  let id = "";

  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage();
    id = await uploadAndWait(page, "e2e-flow.xlsx", DIRTY);
    await page.close();
  });

  test.afterAll(async ({ browser }) => {
    const page = await browser.newPage();
    await deleteByName(page, "e2e-flow.xlsx");
    await page.close();
  });

  test("overview shows six issues with severity counts", async ({ page }) => {
    await page.goto(`/w/${id}`, { waitUntil: "networkidle" });
    await expect(page.getByText("What this workbook does")).toBeVisible();
    for (const [label, value] of [["High", "3"], ["Medium", "1"], ["Low", "2"]]) {
      const card = page.locator("dl > div", { hasText: label }).first();
      await expect(card).toContainText(value);
    }
  });

  test("issue chips navigate to the right sheet", async ({ page }) => {
    await page.goto(`/w/${id}/issues`, { waitUntil: "networkidle" });
    const links = page.locator('a[href*="/sheets/"]');
    expect(await links.count()).toBeGreaterThanOrEqual(6);
    // Every chip: click → lands on its sheet (and group anchor when present).
    const hrefs: Array<string | null> = [];
    for (let i = 0; i < 6; i++) {
      hrefs.push(await links.nth(i).getAttribute("href"));
    }
    for (const href of hrefs) {
      expect(href).toMatch(/\/sheets\/(Inputs|Pricing|Settings|Summary)/);
      await page.goto(href!.startsWith("/") ? href! : `/${href}`, {
        waitUntil: "networkidle",
      });
      await expect(page.locator("h1")).toBeVisible();
    }
    await page.screenshot({ path: `${SHOTS}/issues.png` });
  });

  test("dependency map renders sheet nodes", async ({ page }) => {
    await page.goto(`/w/${id}`, { waitUntil: "networkidle" });
    await page.locator(".react-flow__node").first().waitFor({ timeout: 30000 });
    const count = await page.locator(".react-flow__node").count();
    expect(count).toBe(4);
    await page.screenshot({ path: `${SHOTS}/map.png` });
  });

  test("ask drawer answers with chips and formulas", async ({ page }) => {
    await page.goto(`/w/${id}`, { waitUntil: "networkidle" });
    await page.getByRole("button", { name: "Ask a question" }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.locator("#ask-input").fill("Where does the total with surcharge come from?");
    await page.getByRole("button", { name: "Ask", exact: true }).click();
    await page.getByLabel("Cited cells").waitFor({ timeout: 300000 });
    const chips = page.getByLabel("Cited cells").locator("a");
    expect(await chips.count()).toBeGreaterThan(0);
    const first = await chips.first().innerText();
    expect(first).toContain("Summary!B5");
    await page.getByText("Traced formulas", { exact: false }).click();
    await expect(page.locator("details li code").first()).toContainText("=");
    await page.screenshot({ path: `${SHOTS}/ask.png` });
  });

  test("export downloads non-empty markdown", async ({ page }) => {
    await page.goto(`/w/${id}`, { waitUntil: "networkidle" });
    const [download] = await Promise.all([
      page.waitForEvent("download", { timeout: 60000 }),
      page.getByRole("button", { name: "Export Markdown" }).click(),
    ]);
    const file = await download.path();
    expect(file).toBeTruthy();
    const text = fs.readFileSync(file!, "utf8");
    expect(text.length).toBeGreaterThan(500);
    for (const marker of [
      "## Overview",
      "## Sheets",
      "## Suspicious cells",
      "## Limitations",
      "| Severity |",
    ]) {
      expect(text).toContain(marker);
    }
  });
});
