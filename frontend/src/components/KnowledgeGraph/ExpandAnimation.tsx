interface Props {
  label: string;
}

export function ExpandAnimation({ label }: Props) {
  return (
    <div className="kg-expand-overlay">
      <div className="kg-expand-card">
        <div className="kg-expand-orb-wrap">
          <span className="kg-expand-orb" />
          <span className="kg-expand-orb-ring" />
          <span className="kg-expand-orb-ring-outer" />
        </div>
        <div className="kg-expand-text">
          <span className="kg-expand-title">Searching knowledge base</span>
          <span className="kg-expand-sub">Exploring connections for <strong>{label}</strong></span>
        </div>
        <div className="kg-expand-bar">
          <div className="kg-expand-bar-fill" />
        </div>
      </div>
    </div>
  );
}