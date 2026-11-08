// Captures UI screenshots of a running GigBid for the README / report:
//   BASE=https://gigbid.onrender.com EMAIL=... PASSWORD=... OUT=../../docs/images node tests/capture/capture.mjs
import { chromium } from "@playwright/test";

const BASE = process.env.BASE ?? "http://localhost:8000";
const OUT = process.env.OUT ?? "../../docs/images";
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
const shot = async (name) => { await page.waitForTimeout(1500); await page.screenshot({ path: `${OUT}/ui_${name}.png` }); console.log("shot", name); };

await page.goto(`${BASE}/login`, { timeout: 120000 });
await page.getByTestId("email").fill(process.env.EMAIL);
await page.getByTestId("password").fill(process.env.PASSWORD);
await page.getByTestId("submit").click();
await page.getByRole("heading", { name: "Job inbox" }).waitFor({ timeout: 120000 });
await page.getByTestId("inbox-list").waitFor({ timeout: 120000 });
await shot("01_inbox");

await page.getByTestId("inbox-list").locator("a").first().click();
await page.getByText("Requirement → evidence").waitFor({ timeout: 60000 });
await shot("02_job_detail");

await page.goto(`${BASE}/studio`);
await page.getByTestId("approval-list").locator("a").first().click();
await page.getByTestId("draft").waitFor({ timeout: 60000 });
await shot("03_studio");
const claim = page.getByTestId("claim").first();
if (await claim.count()) { await claim.hover(); await shot("04_evidence_hover"); }

await page.goto(`${BASE}/runs`);
await page.locator("table a").first().click();
await page.getByText("Run timeline").waitFor({ timeout: 60000 });
await shot("05_run_viewer");

for (const [path, name] of [["/pipeline", "06_pipeline"], ["/analytics", "07_analytics"], ["/settings", "08_settings"]]) {
  await page.goto(`${BASE}${path}`);
  await shot(name);
}
const phone = await browser.newPage({ ...{ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true } });
await phone.context().addCookies(await page.context().cookies());
await phone.goto(`${BASE}/inbox`);
await phone.waitForTimeout(3000);
await phone.screenshot({ path: `${OUT}/ui_09_mobile.png` });
console.log("shot 09_mobile");
await browser.close();
