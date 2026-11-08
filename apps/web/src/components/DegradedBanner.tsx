import { api, call } from "@/lib/api/client";
import { useLoad } from "@/lib/hooks";

// Polls /api/health. When the marketplace MCP server (or GigSim/Upwork behind it) is down,
// the circuit breaker opens, analysis is queued, and this banner tells the user so.
export function DegradedBanner() {
  const h = useLoad(() => call(api.GET("/api/health")), [], 10000);
  if (h.error) {
    return <div className="banner danger" role="alert" data-testid="degraded-banner"><strong>GigBid API unreachable.</strong> Retrying…</div>;
  }
  if (!h.data || !h.data.degraded) return null;
  const queued = (h.data.queue as Record<string, number>)?.pending ?? 0;
  return (
    <div className="banner warn" role="alert" data-testid="degraded-banner">
      <strong>Marketplace unavailable.</strong>
      <span className="small">
        GigBid can't reach the {h.data.mode === "upwork_live" ? "Upwork" : "GigSim"} marketplace right now. New analyses are queued
        ({queued} pending) and resume automatically when it recovers. Nothing is sent while it is down.
      </span>
    </div>
  );
}