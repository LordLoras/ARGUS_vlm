import { RotateCcw, Search } from "lucide-react";

import { categories, riskLabels } from "../lib/taxonomy";
import { Button } from "./ui/Button";
import { Card, CardTitle } from "./ui/Card";
import { Input, Select } from "./ui/Form";

export type LibraryFilters = {
  q: string;
  category: string;
  brand: string;
  sensitiveOnly: boolean;
  hasRiskTags: boolean;
  risk: string;
};

export function FilterSidebar({
  filters,
  onChange,
  onClear
}: {
  filters: LibraryFilters;
  onChange: (filters: LibraryFilters) => void;
  onClear: () => void;
}) {
  return (
    <Card className="sticky top-7 h-fit w-72 shrink-0">
      <div className="mb-4 flex items-center justify-between">
        <CardTitle>Filters</CardTitle>
        <Button variant="ghost" className="h-8 px-2" onClick={onClear}>
          <RotateCcw className="h-4 w-4" />
          Clear
        </Button>
      </div>

      <div className="space-y-5">
        <label className="block">
          <span className="mb-2 flex items-center gap-2 text-xs uppercase text-muted-foreground">
            <Search className="h-3.5 w-3.5" />
            Search
          </span>
          <Input
            value={filters.q}
            onChange={(event) => onChange({ ...filters, q: event.target.value })}
            placeholder="brand, OCR, transcript"
            className="w-full"
          />
        </label>

        <div className="space-y-3">
          <label className="flex items-center justify-between gap-3 text-sm">
            Sensitive only
            <input
              type="checkbox"
              checked={filters.sensitiveOnly}
              onChange={(event) => onChange({ ...filters, sensitiveOnly: event.target.checked })}
              className="h-4 w-4 accent-violet-500"
            />
          </label>
          <label className="flex items-center justify-between gap-3 text-sm">
            Has risk tags
            <input
              type="checkbox"
              checked={filters.hasRiskTags}
              onChange={(event) => onChange({ ...filters, hasRiskTags: event.target.checked })}
              className="h-4 w-4 accent-violet-500"
            />
          </label>
        </div>

        <label className="block">
          <span className="mb-2 block text-xs uppercase text-muted-foreground">Category</span>
          <Select
            value={filters.category}
            onChange={(event) => onChange({ ...filters, category: event.target.value })}
            className="w-full"
          >
            <option value="">All categories</option>
            {categories.map((category) => (
              <option key={category} value={category}>
                {category}
              </option>
            ))}
          </Select>
        </label>

        <label className="block">
          <span className="mb-2 block text-xs uppercase text-muted-foreground">Brand</span>
          <Input
            value={filters.brand}
            onChange={(event) => onChange({ ...filters, brand: event.target.value })}
            placeholder="type a brand"
            className="w-full"
          />
        </label>

        <label className="block">
          <span className="mb-2 block text-xs uppercase text-muted-foreground">Risk labels</span>
          <Select
            value={filters.risk}
            onChange={(event) => onChange({ ...filters, risk: event.target.value })}
            className="w-full"
          >
            <option value="">Any observation tag</option>
            {riskLabels.map((label) => (
              <option key={label} value={label}>
                {label}
              </option>
            ))}
          </Select>
        </label>
      </div>
    </Card>
  );
}
