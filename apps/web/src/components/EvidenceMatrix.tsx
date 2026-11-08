type Match = { requirement: string; status: string; skills?: string[]; evidence?: { item_id: string; title?: string | null; type?: string | null; support?: number }[] };

// Requirement-to-evidence matrix: each requirement and the portfolio items that prove it.
export function EvidenceMatrix({ matrix }: { matrix: Match[] }) {
  if (!matrix?.length) return <p className="muted">No requirements extracted.</p>;
  return (
    <div className="table-wrap">
      <table className="matrix">
        <thead><tr><th>Requirement</th><th>Status</th><th>Evidence</th></tr></thead>
        <tbody>
          {matrix.map((m, i) => (
            <tr key={i}>
              <td>{m.requirement}</td>
              <td><span className={`badge ${m.status === "supported" ? "ok" : m.status === "partial" ? "warn" : "danger"}`}>{m.status}</span></td>
              <td>
                {(m.evidence ?? []).length === 0 && <span className="muted small">none - will not be claimed</span>}
                {(m.evidence ?? []).map((e) => (
                  <div key={e.item_id} className="small"><span className="badge">{e.type}</span> {e.title ?? e.item_id}
                    {e.support != null && <span className="muted mono"> · {Math.round(e.support * 100)}%</span>}</div>
                ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}