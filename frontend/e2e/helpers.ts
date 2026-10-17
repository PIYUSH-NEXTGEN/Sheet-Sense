import { expect, type Page } from "@playwright/test";
import path from "node:path";

export const SHOTS = path.join(import.meta.dirname, "../../docs/screenshots");

/** Upload a fixture and wait for auto-navigation to its ready overview. */
export async function uploadAndWait(
  page: Page,
  filename: string,
  content: Buffer,
): Promise<string> {
  await page.goto("/");
  await page.getByRole("button", { name: /choose an .xlsx/i }).waitFor();
  await page.locator('input[type="file"]').setInputFiles({
    name: filename,
    mimeType:
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    buffer: content,
  });
  await page.waitForURL(/\/w\/[a-f0-9]+$/, { timeout: 240000 });
  const id = page.url().split("/w/")[1];
  await expect(page.getByText("What this workbook does")).toBeVisible({
    timeout: 60000,
  });
  return id;
}

export async function deleteByName(page: Page, filename: string) {
  await page.goto("/");
  await page
    .getByRole("button", { name: `Delete ${filename}` })
    .click();
  await expect(page.getByRole("link", { name: filename })).toHaveCount(0, {
    timeout: 15000,
  });
}
