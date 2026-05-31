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
          <button className="clear-link" type="button" onClick={onClear}>
            clear all
          </button>
        </div>
        <input
          className="input"
          aria-label="Search library"
          name="library_search"
          placeholder="Transcript, OCR, brand…"
          value={filters.q}
          onChange={(e) => onChange({ ...filters, q: e.target.value })}
        />
      </div>

      <div className="filter-group">
        <div className="filter-head">
          <span>Quick filters</span>
        </div>
        <button
          type="button"
          className="switch-row"
          aria-pressed={filters.hasRiskTags}
          onClick={() => onChange({ ...filters, hasRiskTags: !filters.hasRiskTags })}
        >
          <span className={`switch ${filters.hasRiskTags ? "on" : ""}`} />
          <span className="switch-label">Has observation tags</span>
          <span className="count">{counts.hasRisk}</span>
        </button>
      </div>

      <div className="filter-group">
        <div className="filter-head">
          <span>Category</span>
        </div>
        {categories.map((category) => {
          const active = filters.category === category;
          return (
            <button
              type="button"
              key={category}
              className="check-row"
              aria-pressed={active}
              onClick={() => onChange({ ...filters, category: active ? "" : category })}
            >
              <span className={`check ${active ? "on" : ""}`} />
              <span>{category}</span>
              <span className="count">{counts.byCategory[category] ?? 0}</span>
            </button>
          );
        })}
      </div>

      <div className="filter-group">
        <div className="filter-head">
          <span>Brand</span>
        </div>
        <input
          className="input"
          aria-label="Filter by brand"
          name="library_brand"
          placeholder="fastloan, aurora, jeep…"
          value={filters.brand}
          onChange={(e) => onChange({ ...filters, brand: e.target.value })}
        />
      </div>

      <div className="filter-group">
        <div className="filter-head">
          <span>Observation tags</span>
          <span className="filter-count">
            {activeRisks.length} / {riskLabels.length}
          </span>
        </div>
        <div className="pill-row">
          {riskLabels.map((label) => (
            <button
              type="button"
              key={label}
              className={`tag-pill ${activeRisks.includes(label) ? "on" : ""}`}
              aria-pressed={activeRisks.includes(label)}
              onClick={() => toggleRisk(label)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
    </aside>
  );
}
