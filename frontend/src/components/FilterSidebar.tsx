import { categories, riskLabels } from "../lib/taxonomy";

export type LibraryFilters = {
  q: string;
  category: string;
  brand: string;
  hasRiskTags: boolean;
  risk: string;
};

type Counts = {
  total: number;
  hasRisk: number;
  byCategory: Record<string, number>;
  byRisk: Record<string, number>;
};

export function FilterSidebar({
  filters,
  counts,
  onChange,
  onClear
}: {
  filters: LibraryFilters;
  counts: Counts;
  onChange: (filters: LibraryFilters) => void;
  onClear: () => void;
}) {
  const activeRisks = filters.risk ? filters.risk.split(",").filter(Boolean) : [];
  const toggleRisk = (label: string) => {
    const set = new Set(activeRisks);
    set.has(label) ? set.delete(label) : set.add(label);
    onChange({ ...filters, risk: Array.from(set).join(",") });
  };

  return (
    <aside className="filters">
      <div className="filter-group">
        <div className="filter-head">
          <span>Search</span>
          <span className="clear-link" onClick={onClear}>
            clear all
          </span>
        </div>
        <input
          className="input"
          placeholder="Transcript, OCR, brand…"
          value={filters.q}
          onChange={(e) => onChange({ ...filters, q: e.target.value })}
        />
      </div>

      <div className="filter-group">
        <div className="filter-head">
          <span>Quick filters</span>
        </div>
        <div
          className="switch-row"
          onClick={() => onChange({ ...filters, hasRiskTags: !filters.hasRiskTags })}
        >
          <span className={`switch ${filters.hasRiskTags ? "on" : ""}`} />
          <span className="switch-label">Has observation tags</span>
          <span className="count">{counts.hasRisk}</span>
        </div>
      </div>

      <div className="filter-group">
        <div className="filter-head">
          <span>Category</span>
        </div>
        {categories.map((category) => {
          const active = filters.category === category;
          return (
            <div
              key={category}
              className="check-row"
              onClick={() => onChange({ ...filters, category: active ? "" : category })}
            >
              <span className={`check ${active ? "on" : ""}`} />
              <span>{category}</span>
              <span className="count">{counts.byCategory[category] ?? 0}</span>
            </div>
          );
        })}
      </div>

      <div className="filter-group">
        <div className="filter-head">
          <span>Brand</span>
        </div>
        <input
          className="input"
          placeholder="fastloan, aurora, jeep…"
          value={filters.brand}
          onChange={(e) => onChange({ ...filters, brand: e.target.value })}
        />
      </div>

      <div className="filter-group">
        <div className="filter-head">
          <span>Risk labels</span>
          <span className="clear-link">
            {activeRisks.length} / {riskLabels.length}
          </span>
        </div>
        <div className="pill-row">
          {riskLabels.map((label) => (
            <span
              key={label}
              className={`tag-pill ${activeRisks.includes(label) ? "on" : ""}`}
              onClick={() => toggleRisk(label)}
            >
              {label}
            </span>
          ))}
        </div>
      </div>

      <div className="filter-group">
        <div className="filter-head">
          <span>Date range</span>
        </div>
        <div
          className="row"
          style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--fg-mute)" }}
        >
          <span>last 30d</span>
          <div style={{ flex: 1, height: 1, background: "var(--border)" }} />
          <span>today</span>
        </div>
      </div>

      <div className="filter-group">
        <div className="filter-head">
          <span>Status</span>
        </div>
        {["completed", "processing", "failed", "duplicate"].map((status) => (
          <div key={status} className="check-row">
            <span className="check" />
            <span>{status}</span>
          </div>
        ))}
      </div>
    </aside>
  );
}
