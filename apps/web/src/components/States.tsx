export function Loading({ rows = 3, label = "Loading" }: { rows?: number; label?: string }) {
  return (
    <div className="stack" role="status" aria-label={label}>
      {Array.from({ length: rows }).map((_, i) => <div key={i} className="skeleton" />)}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="empty card">
      <h3>{title}</h3>
      {children && <div className="small">{children}</div>}
    </div>
  );
}

export function ErrorState({ error, retry }: { error: string; retry?: () => void }) {
  const unavailable = /503|unavailable/i.test(error);
  return (
    <div className="banner danger" role="alert">
      <strong>{unavailable ? "Marketplace unavailable." : "Something went wrong."}</strong>
      <span className="small">{unavailable ? "Your work is queued and will resume automatically." : error}</span>
      {retry && <button onClick={retry}>Retry</button>}
    </div>
  );
}