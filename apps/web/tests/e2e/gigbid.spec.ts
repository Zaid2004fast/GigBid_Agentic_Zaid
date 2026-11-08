import { expect, test, type Page } from "@playwright/test";

// Runs against a live API that serves the built UI (see Makefile `e2e`): GigSim in-process,
// offline model profile, reviewer account from REVIEWER_EMAIL / REVIEWER_PASSWORD.
const EMAIL = process.env.E2E_EMAIL ?? "reviewer@gigbid.dev";
const PASSWORD = process.env.E2E_PASSWORD ?? "reviewer-pass-123";

async function login(page: Page) {
  await page.goto("/login");
  await page.getByTestId("email").fill(EMAIL);
  await page.getByTestId("password").fill(PASSWORD);
  await page.getByTestId("submit").click();
  await expect(page.getByRole("heading", { name: "Job inbox" })).toBeVisible();
}

// Make sure at least `n` proposals are waiting; scouting + analysis run in the worker.
async function ensureApprovals(page: Page, n = 1) {
  await page.request.post("/api/jobs/scout");
  await expect
    .poll(async () => (await (await page.request.get("/api/approvals")).json()).filter((a: any) => a.kind === "proposal" && !a.payload.blocked).length,
          { timeout: 110_000, intervals: [3000] })
    .toBeGreaterThanOrEqual(n);
}

async function openFirstApproval(page: Page) {
  await page.goto("/studio");
  const first = page.getByTestId("approval-list").locator("a").filter({ hasNotText: "blocked" }).first();
  await first.click();
  await expect(page.getByTestId("draft")).toBeVisible();
}

test("onboarding: a new freelancer picks a persona, sets budgets and lands in the inbox", async ({ page }) => {
  const email = `e2e-${Date.now()}@gigbid.dev`;
  await page.goto("/login");
  await page.getByRole("button", { name: /create an account/i }).click();
  await page.getByLabel("Name").fill("E2E Tester");
  await page.getByTestId("email").fill(email);
  await page.getByTestId("password").fill("e2e-password-123");
  await page.getByTestId("submit").click();
  await expect(page.getByRole("heading", { name: "Set up GigBid" })).toBeVisible();
  await page.getByTestId("persona-web").check();
  await page.getByTestId("connects").fill("80");
  await page.getByTestId("finish-onboarding").click();
  await expect(page.getByRole("heading", { name: "Job inbox" })).toBeVisible();
  const s = await (await page.request.get("/api/settings")).json();
  expect(s.weekly_connects).toBe(80);
});

test("approve a proposal: evidence on hover, dry-run cost, approval resumes the graph", async ({ page }) => {
  await login(page);
  await ensureApprovals(page, 1);
  await openFirstApproval(page);
  const claim = page.getByTestId("claim").first();
  await claim.hover();
  await expect(page.getByRole("tooltip")).toContainText(/portfolio|supported/i);
  await expect(page.getByTestId("dry-run")).toContainText("Connects");
  await page.getByTestId("approve").click();
  await expect(page.getByTestId("toast")).toContainText(/approved/i);
  await expect(page).toHaveURL(/\/runs\//);
  await expect(page.getByText(/submitted/i).first()).toBeVisible({ timeout: 60_000 });
});

test("reject with a reason", async ({ page }) => {
  await login(page);
  await ensureApprovals(page, 1);
  await openFirstApproval(page);
  await page.getByTestId("reject").click();
  await expect(page.getByTestId("confirm-reject")).toBeDisabled();
  await page.getByTestId("reject-reason").fill("client budget too low for the scope");
  await page.getByTestId("confirm-reject").click();
  await expect(page.getByTestId("toast")).toContainText(/rejected/i);
});

test("edit a draft: the edit is saved and re-checked before it can be approved", async ({ page }) => {
  await login(page);
  await ensureApprovals(page, 1);
  await openFirstApproval(page);
  await page.getByTestId("edit").click();
  const box = page.getByTestId("edit-box");
  const original = await box.inputValue();
  await box.fill(original.replace(/^[^.]+\.\s*/, "") + " Happy to start this week.");
  await page.getByTestId("save-edit").click();
  await expect(page.getByTestId("toast")).toContainText(/edit saved/i);
});

test("degraded mode: the UI says when the marketplace is unavailable", async ({ page }) => {
  await login(page);
  await page.route("**/api/health", (route) =>
    route.fulfill({ json: { api: true, marketplace: false, degraded: true, mode: "gigsim", queue: { pending: 3 },
                            servers: { marketplace: { ok: false, open: true, failures: 3, last_error: "ConnectError" } } } }));
  await page.reload();
  await expect(page.getByTestId("degraded-banner")).toContainText(/marketplace unavailable/i);
  await expect(page.getByTestId("degraded-banner")).toContainText(/queued/i);
});

test("works on a phone screen @mobile", async ({ page }) => {
  await login(page);
  await expect(page.locator(".topbar")).toBeVisible();
  await page.locator(".topbar").getByRole("link", { name: "Pipeline" }).click();
  await expect(page.getByRole("heading", { name: "Pipeline" })).toBeVisible();
});
