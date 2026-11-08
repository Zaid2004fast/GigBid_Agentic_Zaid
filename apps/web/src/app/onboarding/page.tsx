import { useState } from "react";
import { api, call } from "@/lib/api/client";

const PERSONAS = [
  { id: "aiml", name: "AI/ML engineer", floor: 45, fixed: 400, cat: "AI & Machine Learning" },
  { id: "web", name: "Full-stack web developer", floor: 35, fixed: 300, cat: "Web Development" },
  { id: "data", name: "Data analyst", floor: 30, fixed: 250, cat: "Data Analytics" },
  { id: "own", name: "My own profile (upload my portfolio)", floor: 30, fixed: 250, cat: "" },
] as const;

export default function OnboardingPage() {
  const [persona, setPersona] = useState<(typeof PERSONAS)[number]["id"]>("aiml");
  const p = PERSONAS.find((x) => x.id === persona)!;
  const [floor, setFloor] = useState<number>(p.floor);
  const [fixed, setFixed] = useState<number>(p.fixed);
  const [connects, setConnects] = useState(120);
  const [market, setMarket] = useState<"gigsim" | "upwork_live">("gigsim");
  const [file, setFile] = useState<File | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function finish() {
    setBusy(true);
    setErr(null);
    try {
      await call(api.POST("/api/onboarding", { body: { persona, marketplace: market, floor_hourly: floor, min_fixed: fixed, weekly_connects: connects,
        search_category: p.cat, search_query: "" } }));
      if (file) {
        const fd = new FormData();
        fd.append("file", file);
        const r = await fetch("/api/portfolio/upload", { method: "POST", body: fd, credentials: "include" });
        if (!r.ok) throw new Error(`upload failed (${r.status})`);
      }
      if (market === "upwork_live") {
        const r = await call(api.GET("/api/accounts/upwork/start"));
        window.location.href = (r as { authorize_url: string }).authorize_url;
        return;
      }
      window.location.assign("/inbox");   // fresh boot: no stale onboarding state
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth">
      <div className="card stack" style={{ width: "min(640px, 100%)" }}>
        <h1>Set up GigBid</h1>
        <fieldset className="stack" style={{ border: 0, padding: 0 }}>
          <legend><strong>1. Who are you bidding as?</strong></legend>
          {PERSONAS.map((x) => (
            <label key={x.id} className="row" style={{ flexDirection: "row" }}>
              <input type="radio" name="persona" style={{ width: "auto", minHeight: 0 }} checked={persona === x.id}
                     onChange={() => { setPersona(x.id); setFloor(x.floor); setFixed(x.fixed); }} data-testid={`persona-${x.id}`} />
              <span>{x.name}</span>
            </label>
          ))}
        </fieldset>
        <div>
          <strong>2. Connect a marketplace</strong>
          <div className="row" style={{ marginTop: 6 }}>
            <button type="button" className={market === "gigsim" ? "btn-primary" : ""} onClick={() => setMarket("gigsim")}>GigSim (simulator)</button>
            <button type="button" className={market === "upwork_live" ? "btn-primary" : ""} onClick={() => setMarket("upwork_live")}>Upwork (OAuth)</button>
          </div>
          <p className="muted small">Upwork uses the official MCP server; every write is a draft you confirm on Upwork.</p>
        </div>
        <label><span>3. Upload a case study (Markdown, optional)</span>
          <input type="file" accept=".md,.markdown,.txt" onChange={(e) => setFile(e.target.files?.[0] ?? null)} data-testid="upload" /></label>
        <div className="field-row">
          <label><span>Hourly floor ($)</span><input type="number" value={floor} min={5} onChange={(e) => setFloor(+e.target.value)} data-testid="floor" /></label>
          <label><span>Min fixed price ($)</span><input type="number" value={fixed} min={0} onChange={(e) => setFixed(+e.target.value)} /></label>
          <label><span>Weekly Connects budget</span><input type="number" value={connects} min={0} onChange={(e) => setConnects(+e.target.value)} data-testid="connects" /></label>
        </div>
        {err && <div className="banner danger" role="alert">{err}</div>}
        <button className="btn-primary" onClick={finish} disabled={busy} data-testid="finish-onboarding">Start scouting</button>
      </div>
    </div>
  );
}