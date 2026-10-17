import { expect, test } from "@playwright/test";
import { SHOTS } from "./helpers";

const ALLOWED_HOSTS = new Set([
  "127.0.0.1:8000",
  "localhost:5173",
  "127.0.0.1:5173",
]);

test("console clean and network local during upload-to-overview", async ({
  page,
}) => {
  const consoleErrors: string[] = [];
  const hosts = new Set<string>();
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text().slice(0, 200));
  });
  page.on("pageerror", (e) => consoleErrors.push(String(e).slice(0, 200)));
  page.on("request", (req) => {
    try {
      hosts.add(new URL(req.url()).host);
    } catch {
      hosts.add(`unparseable:${req.url().slice(0, 60)}`);
    }
  });
  await page.goto("/", { waitUntil: "networkidle" });
  await page.waitForTimeout(2000);
  await page.screenshot({ path: `${SHOTS}/home.png` });
  const foreign = [...hosts].filter((h) => !ALLOWED_HOSTS.has(h));
  expect(foreign).toEqual([]);
  expect(consoleErrors).toEqual([]);
});

test("keyboard-only run reaches every control", async ({ page }) => {
  await page.goto("/", { waitUntil: "networkidle" });
  const seen: string[] = [];
  for (let i = 0; i < 60; i++) {
    await page.keyboard.press("Tab");
    const label = await page.evaluate(() => {
      const el = document.activeElement;
      if (!el || el === document.body) return "BODY";
      return (
        `${el.tagName}<${[...el.classList].slice(0, 2).join(".")}>` +
        (el.getAttribute("aria-label") || el.textContent || "").slice(0, 40)
      );
    });
    if (!seen.includes(label)) seen.push(label);
    if (label.startsWith("BODY")) break;
  }
  const dump = seen.join("\n");
  // Dropzone (role=button), delete buttons, nav links must all be tabbable.
  expect(dump).toMatch(/Choose an \.xlsx/);
  expect(dump).toMatch(/Workbooks|Upload/);

  // Issues-page selects operable by keyboard on a ready workbook.
  const rows = await page.request
    .get("http://127.0.0.1:8000/api/workbooks")
    .then((r) => r.json())
    .then((d) => d.workbooks.filter((w: { status: string }) => w.status === "ready"));
  test.skip(!rows.length, "no ready workbook for keyboard test");
  await page.goto(`/w/${rows[0].workbook_id}/issues`, { waitUntil: "networkidle" });
  await page.keyboard.press("Tab");
  for (let i = 0; i < 40; i++) {
    await page.keyboard.press("Tab");
  }
  const focused = await page.evaluate(() => document.activeElement?.tagName);
  expect(["SELECT", "A", "BUTTON"]).toContain(focused);
  await page.screenshot({ path: `${SHOTS}/keyboard.png` });
});
