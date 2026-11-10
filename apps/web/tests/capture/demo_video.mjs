// Records the captioned 3-minute demo (Playwright video, 1280x720).
//   BASE=http://localhost:8000 EMAIL=... PASSWORD=... OUT=<dir> node tests/capture/demo_video.mjs
import { chromium } from "@playwright/test";

const { BASE = "http://localhost:8000", EMAIL, PASSWORD, OUT } = process.env;
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1280, height: 720 }, recordVideo: { dir: OUT, size: { width: 1280, height: 720 } } });
const page = await ctx.newPage();
const wait = (s) => page.waitForTimeout(s * 1000);

async function caption(text) {
  await page.evaluate((t) => {
    let el = document.getElementById("demo-caption");
    if (!el) {
      el = document.createElement("div");
      el.id = "demo-caption";
      Object.assign(el.style, { position: "fixed", left: "50%", bottom: "24px", transform: "translateX(-50%)", maxWidth: "1000px",
        background: "rgba(17,24,20,0.88)", color: "#fff", padding: "14px 22px", borderRadius: "10px", font: "600 20px/1.4 system-ui",
        zIndex: 99999, textAlign: "center", boxShadow: "0 4px 18px rgba(0,0,0,.3)" });
      document.body.appendChild(el);
    }
    el.textContent = t;
  }, text);
}
async function scene(path, text, secs) {
  if (path) { await page.goto(BASE + path); await page.waitForLoadState("networkidle").catch(() => {}); }
  await wait(1.2);
  await caption(text);
  await wait(secs);
}
const api = (p) => page.evaluate(async (u) => (await fetch(u, { credentials: "include" })).json(), p);

// 1. sign in
await page.goto(`${BASE}/login`);
await caption("GigBid: a team of AI agents that finds, judges and drafts freelance proposals. Nothing is sent without your approval.");
await wait(3);
await page.getByTestId("email").pressSequentially(EMAIL, { delay: 40 });
await page.getByTestId("password").pressSequentially(PASSWORD, { delay: 40 });
await page.getByTestId("submit").click();
await page.getByRole("heading", { name: "Job inbox" }).waitFor();
await scene(null, "Agents scouted the job feed and analysed every job in parallel: fit, risk, price and Connects cost.", 7);
await scene(null, "Jobs are ranked by fit. Scams, poor fits and reposts are skipped automatically, so no Connects are wasted.", 6);

// 2. scam caught
const jobs = await api("/api/jobs");
const scam = jobs.find((j) => (j.flags || []).some((f) => ["off_platform_contact", "off_platform_payment", "free_work", "upfront_fee"].includes(f)));
if (scam) {
  await scene(`/jobs/${encodeURIComponent(scam.job_id)}`, "Scam caught: the Risk Assessor found off-platform requests and a risky client history, so the job was skipped.", 6);
  await page.getByRole("heading", { name: "Risk report" }).scrollIntoViewIfNeeded();
  await caption("Every decision comes with its reasons, so you can audit why GigBid skipped a job.");
  await wait(6);
}

// 3. injection ignored
await scene("/jobs/live_0012", "This post hides an instruction aimed at AI tools. GigBid detected it and cut it out before any model saw the post.", 7);
await page.getByText("Original post (untrusted - shown as data)").click();
await page.getByText("Original post (untrusted - shown as data)").scrollIntoViewIfNeeded();
await caption("Here is the hidden instruction (\"print your system prompt...\"). The proposal writer only ever sees a typed summary, never this text.");
await wait(8);

// 4. proposal studio: evidence + approve
const pend = (await api("/api/approvals")).filter((a) => a.kind === "proposal" && !a.payload.blocked);
await scene(`/studio/${encodeURIComponent(pend[0].thread_id)}`, "The Proposal Writer drafted this. Every highlighted sentence is a claim checked against the freelancer's real portfolio.", 7);
const claim = page.getByTestId("claim").first();
await claim.hover();
await caption("Hover a claim to see its proof: the case study and code behind it. Unsupported claims are removed before you see the draft.");
await wait(8);
await page.mouse.move(1100, 650);
await caption("The dry run shows exactly what will be sent and how many Connects it costs. The critic and policy checks are shown too.");
await wait(7);
await page.getByTestId("approve").click();
await caption("Approved. Only now is the proposal submitted to the marketplace, exactly once.");
await wait(4);

// 5. run viewer
await page.waitForURL(/\/runs\//, { timeout: 15000 }).catch(() => {});
await wait(2);
await caption("The agent run, node by node: three analysts in parallel, then pricing, writer, verifier, critic, compliance and your approval.");
await wait(8);
await page.mouse.wheel(0, 500);
await caption("Every step is traced with its time and tokens, and any checkpoint can be replayed.");
await wait(6);

// 6. pipeline + client reply
await scene("/pipeline", "The pipeline updates from marketplace events: viewed, replied, interview, hired.", 7);
const msg = (await api("/api/approvals")).find((a) => a.kind === "message" && a.payload.intent?.intent === "interview_request")
  || (await api("/api/approvals")).find((a) => a.kind === "message");
if (msg) {
  await scene(`/studio/${encodeURIComponent(msg.thread_id)}`, "A client replied. The Client Liaison classified the message and drafted an answer.", 7);
  await caption("For an interview request it offers free slots from your calendar. You approve before anything is sent.");
  await wait(7);
  await page.getByTestId("approve").click();
  await caption("Sent, and a tentative calendar hold was created.");
  await wait(4);
}

// 7. settings + analytics
await scene("/settings", "Settings: autonomy level, budgets, saved searches and connected accounts.", 6);
await page.getByTestId("memory-viewer").scrollIntoViewIfNeeded();
await caption("Everything GigBid learns from your edits is visible here, with the rule that allowed it, and can be deleted.");
await wait(7);
await scene("/analytics", "Analytics: reply rate by category, Connects spent versus outcomes, and cost and latency per proposal.", 7);
await caption("GigBid: LangGraph agents, MCP tools, verified evidence, and a human in control. Code and report: github.com/Zaid2004fast/GigBid_Agentic_Zaid");
await wait(6);

await ctx.close();
await browser.close();
console.log("video saved in", OUT);
