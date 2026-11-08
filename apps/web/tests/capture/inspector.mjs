// Screenshots of the official MCP Inspector connected to each GigBid MCP server (A7 deliverable).
//   URL=<inspector url with token> PY=<python.exe> RUNNER=<scripts/run_mcp.py> OUT=<docs/images> node tests/capture/inspector.mjs
import { chromium } from "@playwright/test";

const { URL, PY, RUNNER, OUT } = process.env;
const browser = await chromium.launch();
const calls = { portfolio: ["search_evidence", { requirement: "background workers that process uploads" }],
                marketplace: ["get_policy", {}], workspace: ["free_slots", {}] };

for (const server of ["portfolio", "marketplace", "workspace"]) {
  const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
  await page.goto(URL);
  await page.locator("#command-input").fill(PY);
  await page.locator("#arguments-input").fill(`${RUNNER} ${server}`);
  await page.getByRole("button", { name: /^Connect$/ }).click();
  await page.getByRole("tab", { name: /Tools/ }).waitFor({ timeout: 90000 });
  await page.getByRole("tab", { name: /Tools/ }).click();
  await page.getByRole("button", { name: /List Tools/ }).click();
  await page.waitForTimeout(3000);
  await page.screenshot({ path: `${OUT}/inspector_${server}_tools.png` });
  const [tool, args] = calls[server];
  await page.getByText(tool, { exact: true }).first().click();
  for (const [k, v] of Object.entries(args)) {
    const box = page.locator(`#${k}`).or(page.getByLabel(k));
    await box.first().fill(String(v));
  }
  await page.getByRole("button", { name: /Run Tool/ }).click();
  await page.waitForTimeout(server === "portfolio" ? 25000 : 6000);
  await page.screenshot({ path: `${OUT}/inspector_${server}_call.png` });
  console.log("captured", server);
  await page.close();
}
await browser.close();
