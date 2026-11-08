import { useEffect, useState } from "react";
import { api, call, type SettingsModel } from "@/lib/api/client";
import { useLoad } from "@/lib/hooks";
import { ErrorState, Loading } from "@/components/States";

export default function SettingsPage() {
  const s = useLoad(() => call(api.GET("/api/settings")), []);
  const searches = useLoad(() => call(api.GET("/api/settings/searches")), []);
  const mem = useLoad(() => call(api.GET("/api/settings/memory")), []);
  const acc = useLoad(() => call(api.GET("/api/accounts")), []);
  const [form, setForm] = useState<SettingsModel | null>(null);
  const [saved, setSaved] = useState(false);
  const [q, setQ] = useState("");
  useEffect(() => { if (s.data) setForm(s.data); }, [s.data]);
  if (s.error) return <ErrorState error={s.error} retry={s.reload} />;
  if (!form) return <Loading />;
  const set = <K extends keyof SettingsModel>(k: K, v: SettingsModel[K]) => setForm({ ...form, [k]: v });

  async function save() {
    await call(api.PUT("/api/settings", { body: form! }));
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }
  async function addSearch() {
    await call(api.POST("/api/settings/searches", { body: { query: q, category: "", skills: "", interval_minutes: 30, enabled: true } }));
    setQ("");
    searches.reload();
  }
  async function forget(ns: string, key: string) {
    await call(api.DELETE("/api/settings/memory/{namespace}/{key}", { params: { path: { namespace: ns, key } } }));
    mem.reload();
  }
  async function connectUpwork() {
    const r = await call(api.GET("/api/accounts/upwork/start"));
    window.location.href = (r as { authorize_url: string }).authorize_url;
  }
  const style = (mem.data ?? []).filter((m) => m.namespace === "style");
  const cands = (mem.data ?? []).filter((m) => m.namespace === "style_candidates");
  const outcome = (mem.data ?? []).filter((m) => m.namespace === "outcome");
  return (
    <>
      <div className="page-head"><div><h1>Settings</h1><p className="muted">Autonomy, budgets, searches, accounts - and everything GigBid has learned about you.</p></div></div>
      <div className="grid grid-2">
        <section className="card stack">
          <h2>Autonomy and budgets</h2>
          <label><span>Autonomy</span>
            <select value={form.autonomy} onChange={(e) => set("autonomy", e.target.value as SettingsModel["autonomy"])} data-testid="autonomy">
              <option value="suggest">Suggest only (you review every job)</option>
              <option value="auto_skip">Auto-skip clearly low-fit jobs (never auto-send)</option>
            </select></label>
          <div className="field-row">
            <label><span>Hourly floor ($)</span><input type="number" value={form.floor_hourly} onChange={(e) => set("floor_hourly", +e.target.value)} /></label>
            <label><span>Min fixed ($)</span><input type="number" value={form.min_fixed} onChange={(e) => set("min_fixed", +e.target.value)} /></label>
            <label><span>Weekly Connects</span><input type="number" value={form.weekly_connects} onChange={(e) => set("weekly_connects", +e.target.value)} /></label>
          </div>
          <label className="row" style={{ flexDirection: "row" }}><input type="checkbox" style={{ width: "auto", minHeight: 0 }} checked={form.pacing}
                 onChange={(e) => set("pacing", e.target.checked)} /><span>Pace Connects across the week</span></label>
          <label><span>Proposal strategy</span>
            <select value={form.strategy} onChange={(e) => set("strategy", e.target.value as SettingsModel["strategy"])}>
              <option value="evidence_first">Evidence first</option><option value="question_first">Question first</option></select></label>
          <div className="row"><button className="btn-primary" onClick={save}>Save</button>{saved && <span className="badge ok">saved</span>}</div>
        </section>
        <section className="card stack">
          <h2>Connected accounts</h2>
          <p>GigSim: {acc.data?.gigsim ? <span className="badge ok">connected</span> : <span className="badge">not connected</span>}</p>
          <p>Upwork: {acc.data?.upwork ? <span className="badge ok">connected</span> : <button onClick={connectUpwork}>Connect via OAuth</button>}</p>
          <p className="muted small">Tokens are stored encrypted and never logged.</p>
          <h2>Saved searches</h2>
          <ul>{(searches.data ?? []).map((x) => <li key={x.id}>{x.category || x.query || "all jobs"} <span className="muted small">every {x.interval_minutes} min</span></li>)}</ul>
          <div className="row"><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="keywords, e.g. langgraph" aria-label="New saved search" style={{ flex: 1 }} />
            <button onClick={addSearch} disabled={!q.trim()}>Add</button></div>
        </section>
      </div>
      <section className="card stack" style={{ marginTop: 16 }} data-testid="memory-viewer">
        <h2>What GigBid has learned</h2>
        <h3>Style rules (promoted from your edits)</h3>
        {style.length === 0 && <p className="muted small">None yet. A pattern is promoted after it appears in 3 edits across 2 different jobs.</p>}
        {style.map((m) => (
          <div key={m.key} className="spread comment ok">
            <span><strong>{(m.value as any).text}</strong><br /><span className="small muted">{(m.value as any).promotion_rule} · seen {(m.value as any).support}x</span></span>
            <button className="btn-danger small" onClick={() => forget("style", m.key)} aria-label={`Forget ${m.key}`}>Forget</button>
          </div>
        ))}
        <details><summary>Candidates not yet promoted ({cands.length})</summary>
          {cands.map((m) => <div key={m.key} className="spread small"><span>{(m.value as any).text} - {(m.value as any).occurrences} edit(s), {(m.value as any).jobs.length} job(s)</span>
            <button className="btn-ghost small" onClick={() => forget("style_candidates", m.key)}>Forget</button></div>)}
        </details>
        <h3>Outcome memory (per category)</h3>
        {outcome.length === 0 && <p className="muted small">Learned after replies and hires arrive from the marketplace.</p>}
        {outcome.map((m) => (
          <div key={m.key} className="spread comment">
            <span><strong>{m.key}</strong>: {(m.value as any).replied}/{(m.value as any).n} replied, {(m.value as any).hired} hired</span>
            <button className="btn-danger small" onClick={() => forget("outcome", m.key)}>Forget</button>
          </div>
        ))}
      </section>
    </>
  );
}