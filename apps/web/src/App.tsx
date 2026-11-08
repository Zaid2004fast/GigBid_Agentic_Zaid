import { createContext, useContext } from "react";
import { Navigate, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { api, call, type UserOut } from "@/lib/api/client";
import { useLoad } from "@/lib/hooks";
import { DegradedBanner } from "@/components/DegradedBanner";
import LoginPage from "@/app/login/page";
import OnboardingPage from "@/app/onboarding/page";
import InboxPage from "@/app/inbox/page";
import JobPage from "@/app/jobs/[id]/page";
import StudioIndex from "@/app/studio/page";
import StudioPage from "@/app/studio/[id]/page";
import PipelinePage from "@/app/pipeline/page";
import MessagesPage from "@/app/messages/page";
import RunsPage from "@/app/runs/page";
import RunPage from "@/app/runs/[id]/page";
import AnalyticsPage from "@/app/analytics/page";
import SettingsPage from "@/app/settings/page";

type Ctx = { user: UserOut; reload: () => void };
const UserCtx = createContext<Ctx | null>(null);
export const useUser = () => useContext(UserCtx)!;

const NAV = [
  ["/inbox", "Job inbox"],
  ["/studio", "Proposal studio"],
  ["/pipeline", "Pipeline"],
  ["/messages", "Messages"],
  ["/runs", "Agent runs"],
  ["/analytics", "Analytics"],
  ["/settings", "Settings"],
] as const;

function Shell({ children, pending }: { children: React.ReactNode; pending: number }) {
  const links = NAV.map(([to, label]) => (
    <NavLink key={to} to={to} className={({ isActive }) => (isActive ? "active" : "")}>
      <span>{label}</span>
      {to === "/studio" && pending > 0 && <span className="count" aria-label={`${pending} pending approvals`}>{pending}</span>}
    </NavLink>
  ));
  return (
    <div className="shell">
      <aside className="side" aria-label="Main navigation">
        <div className="brand"><span className="brand-dot" aria-hidden>✓</span>GigBid</div>
        <nav className="nav">{links}</nav>
        <p className="muted small" style={{ margin: "24px 10px 0" }}>Nothing reaches a client until you approve it.</p>
      </aside>
      <nav className="topbar" aria-label="Main navigation">{links}</nav>
      <main className="main" id="main">
        <DegradedBanner />
        {children}
      </main>
    </div>
  );
}

export default function App() {
  const loc = useLocation();
  const me = useLoad(() => call(api.GET("/api/auth/me")), [loc.pathname === "/login"]);
  const pending = useLoad(() => (me.data ? call(api.GET("/api/approvals")) : Promise.resolve([])), [me.data?.id], 15000);
  if (loc.pathname === "/login") return <LoginPage onDone={me.reload} />;
  if (me.loading && !me.data) return <div className="auth"><div className="skeleton" style={{ width: 320 }} /></div>;
  if (!me.data) return <Navigate to="/login" replace />;
  if (!me.data.onboarded && loc.pathname !== "/onboarding") return <Navigate to="/onboarding" replace />;
  return (
    <UserCtx.Provider value={{ user: me.data, reload: me.reload }}>
      {loc.pathname === "/onboarding" ? (
        <OnboardingPage />
      ) : (
        <Shell pending={pending.data?.length ?? 0}>
          <Routes>
            <Route path="/" element={<Navigate to="/inbox" replace />} />
            <Route path="/inbox" element={<InboxPage />} />
            <Route path="/jobs/:id" element={<JobPage />} />
            <Route path="/studio" element={<StudioIndex />} />
            <Route path="/studio/:id" element={<StudioPage />} />
            <Route path="/pipeline" element={<PipelinePage />} />
            <Route path="/messages" element={<MessagesPage />} />
            <Route path="/runs" element={<RunsPage />} />
            <Route path="/runs/:id" element={<RunPage />} />
            <Route path="/analytics" element={<AnalyticsPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="*" element={<div className="empty">Page not found. <a href="/inbox">Go to inbox</a></div>} />
          </Routes>
        </Shell>
      )}
    </UserCtx.Provider>
  );
}
