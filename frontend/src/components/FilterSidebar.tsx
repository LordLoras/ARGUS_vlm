import { categories } from "../lib/taxonomy";

export type LibraryFilters = {
  q: string;
  category: string;
  brand: string;
};

type Counts = {
  total: number;
  byCategory: Record<string, number>;
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
    </aside>
  );
}
