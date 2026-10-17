import fs from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";
import { SHOTS, deleteByName, uploadAndWait } from "./helpers";

const DIRTY = fs.readFileSync(
  path.join(
    import.meta.dirname,
    "../../backend/tests/fixtures/harbor-supply-pricing.xlsx",
  ),
);

test("upload by file pick, progress, reach overview", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(String(e).slice(0, 150)));
  const id = await uploadAndWait(page, "e2e-upload.xlsx", DIRTY);
  expect(id).toMatch(/^[a-f0-9]+$/);
  await page.screenshot({ path: `${SHOTS}/overview.png` });
  expect(errors).toEqual([]);
  await deleteByName(page, "e2e-upload.xlsx");
});

test("corrupt file and .xlsm show friendly errors", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: /choose an .xlsx/i }).waitFor();
  await page.locator('input[type="file"]').setInputFiles({
    name: "evil.xlsm",
    mimeType:
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    buffer: Buffer.from("not-a-workbook"),
  });
  await expect(page.getByRole("alert").first()).toContainText(/xlsm|macro/i);
  await page.locator('input[type="file"]').setInputFiles({
    name: "junk.xlsx",
    mimeType:
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    buffer: Buffer.from("definitely not a zip file"),
  });
  await expect(page.getByRole("alert").first()).toContainText(/readable|valid/i);
});
