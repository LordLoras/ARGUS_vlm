import { useCallback, useEffect, useState } from "react";

import { Topbar } from "../components/Topbar";
import { knowledgeApi, type KnowledgeStats, type IABEntry, type BrandRule, type Override, type InferenceRule, type BackfillSuggestion } from "../lib/knowledge-api";
import { cn } from "../lib/utils";

type Tab = "overview" | "product" | "content" | "brands" | "overrides" | "rules" | "backfill";

const TABS: { id: Tab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "product", label: "Product Taxonomy" },
  { id: "content", label: "Content Taxonomy" },
  { id: "brands", label: "Brand Rules" },
  { id: "overrides", label: "Overrides" },
  { id: "rules", label: "Inference Rules" },
  { id: "backfill", label: "Backfill" },
];

export function Taxonomy() {
  const [tab, setTab] = useState<Tab>("overview");
  const [stats, setStats] = useState<KnowledgeStats | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(() => {
    setLoading(true);
    knowledgeApi.stats().then(setStats).finally(() => setLoading(false));
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  return (
    <>
      <Topbar crumbs={["System", "Taxonomy"]} />
      <div className="page">
        <div className="page-head">
          <div>
            <h1 className="page-title">Taxonomy Manager</h1>
            <p className="page-sub">IAB taxonomy, brand rules, overrides, and knowledge base</p>
          </div>
        </div>
        <div style={{ display: "flex", gap: 0, borderBottom: "1px solid var(--border)", marginBottom: 16 }}>
          {TABS.map(t => (
            <button
              key={t.id}
              className={cn("btn", tab === t.id && "btn-primary")}
              style={{ borderRadius: 0, borderBottom: tab === t.id ? "2px solid var(--accent)" : "2px solid transparent", fontWeight: tab === t.id ? 600 : 400 }}
              onClick={() => setTab(t.id)}
            >
              {t.label}
            </button>
          ))}
        </div>
        {loading && !stats ? (
          <div style={{ padding: 32, color: "var(--fg-mute)" }}>Loading...</div>
        ) : tab === "overview" ? (
          <OverviewTab stats={stats} onRefresh={refresh} />
        ) : tab === "product" ? (
          <TaxonomyTab type="product" />
        ) : tab === "content" ? (
          <TaxonomyTab type="content" />
        ) : tab === "brands" ? (
          <BrandRulesTab />
        ) : tab === "overrides" ? (
          <OverridesTab />
        ) : tab === "rules" ? (
          <InferenceRulesTab />
        ) : tab === "backfill" ? (
          <BackfillTab />
        ) : null}
      </div>
    </>
  );
}

// ── Overview Tab ────────────────────────────────────────────

function OverviewTab({ stats, onRefresh }: { stats: KnowledgeStats | null; onRefresh: () => void }) {
  const [loading, setLoading] = useState(false);

  const loadTaxonomies = async () => {
    setLoading(true);
    try {
      await knowledgeApi.loadTaxonomies();
      onRefresh();
    } catch (e) {
      alert("Failed to load taxonomies: " + (e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  if (!stats) return null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 12 }}>
        <StatCard label="Product Taxonomy" value={`${stats.product_taxonomy.active}/${stats.product_taxonomy.total}`} sub="active/total" />
        <StatCard label="Content Taxonomy" value={`${stats.content_taxonomy.active}/${stats.content_taxonomy.total}`} sub="active/total" />
        <StatCard label="Brand Rules" value={String(stats.brand_rules)} />
        <StatCard label="Overrides" value={String(stats.overrides)} />
        <StatCard label="Inference Rules" value={String(stats.inference_rules)} />
        <StatCard label="Corrections" value={String(stats.corrections_logged)} />
      </div>
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <button className="btn btn-primary" disabled={loading} onClick={loadTaxonomies}>
          {loading ? "Loading..." : "Reload IAB Taxonomies from TSV"}
        </button>
        <span style={{ color: "var(--fg-mute)", fontSize: 12 }}>
          Ingests the latest TSV files into the knowledge DB
        </span>
      </div>
      {stats.versions.length > 0 && (
        <div className="dcard">
          <div className="dcard-head"><span>Taxonomy Versions</span></div>
          <table style={{ width: "100%", fontSize: 12 }}>
            <thead>
              <tr><th>Type</th><th>Version</th><th>Entries</th><th>Loaded</th></tr>
            </thead>
            <tbody>
              {stats.versions.map((v, i) => (
                <tr key={i}><td>{v.taxonomy_type}</td><td>{v.version}</td><td>{v.entries_count}</td><td>{v.loaded_at}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="dcard" style={{ padding: "12px 16px" }}>
      <div style={{ fontSize: 10, color: "var(--fg-mute)", marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: 600 }}>{value}</div>
      {sub && <div style={{ fontSize: 10, color: "var(--fg-mute)" }}>{sub}</div>}
    </div>
  );
}

// ── Taxonomy Browser Tab ────────────────────────────────────

function TaxonomyTab({ type }: { type: "product" | "content" }) {
  const [tiers, setTiers] = useState<IABEntry[]>([]);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [searchQ, setSearchQ] = useState("");
  const [searchResults, setSearchResults] = useState<IABEntry[]>([]);
  const [loading, setLoading] = useState(true);

  const listFn = type === "product" ? knowledgeApi.listProduct : knowledgeApi.listContent;
  const searchFn = type === "product" ? knowledgeApi.searchProduct : knowledgeApi.searchContent;
  const toggleFn = type === "product" ? knowledgeApi.toggleProduct : knowledgeApi.toggleContent;

  const loadRoot = useCallback(() => {
    setLoading(true);
    listFn({ active_only: false })
      .then(setTiers)
      .finally(() => setLoading(false));
  }, [listFn]);

  useEffect(() => { loadRoot(); }, [loadRoot]);

  const doSearch = useCallback(() => {
    if (!searchQ.trim()) { setSearchResults([]); return; }
    searchFn(searchQ.trim()).then(setSearchResults);
  }, [searchQ, searchFn]);

  const toggle = async (id: string, active: boolean) => {
    await toggleFn(id, !active);
    loadRoot();
  };

  const toggleExpand = (id: string) => {
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const roots = tiers.filter(t => !t.parent_id);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", gap: 8 }}>
        <input
          className="input"
          style={{ flex: 1 }}
          placeholder={`Search ${type} taxonomy...`}
          value={searchQ}
          onChange={e => setSearchQ(e.target.value)}
          onKeyDown={e => e.key === "Enter" && doSearch()}
        />
        <button className="btn" onClick={doSearch}>Search</button>
        <button className="btn" onClick={loadRoot}>Refresh</button>
      </div>

      {searchResults.length > 0 && (
        <div className="dcard">
          <div className="dcard-head"><span>Search Results ({searchResults.length})</span></div>
          <div style={{ maxHeight: 300, overflow: "auto" }}>
            {searchResults.map(e => (
              <TaxonomyRow key={e.unique_id} entry={e} onToggle={toggle} />
            ))}
          </div>
        </div>
      )}

      {loading ? <div style={{ color: "var(--fg-mute)" }}>Loading...</div> : (
        <div className="dcard">
          <div className="dcard-head"><span>{type === "product" ? "IAB Product" : "IAB Content"} Taxonomy ({roots.length} roots)</span></div>
          <div style={{ maxHeight: 600, overflow: "auto" }}>
            {roots.map(entry => (
              <TaxonomyNode
                key={entry.unique_id}
                entry={entry}
                all={tiers}
                depth={0}
                expanded={expanded}
                onToggleExpand={toggleExpand}
                onToggleActive={toggle}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function TaxonomyNode({ entry, all, depth, expanded, onToggleExpand, onToggleActive }: {
  entry: IABEntry; all: IABEntry[]; depth: number;
  expanded: Set<string>; onToggleExpand: (id: string) => void;
  onToggleActive: (id: string, active: boolean) => void;
}) {
  const children = all.filter(c => c.parent_id === entry.unique_id);
  const hasChildren = children.length > 0;
  const isExpanded = expanded.has(entry.unique_id);

  return (
    <div>
      <TaxonomyRow
        entry={entry}
        depth={depth}
        hasChildren={hasChildren}
        expanded={isExpanded}
        onToggleExpand={() => onToggleExpand(entry.unique_id)}
        onToggle={() => onToggleActive(entry.unique_id, entry.active)}
      />
      {isExpanded && children.map(child => (
        <TaxonomyNode
          key={child.unique_id}
          entry={child}
          all={all}
          depth={depth + 1}
          expanded={expanded}
          onToggleExpand={onToggleExpand}
          onToggleActive={onToggleActive}
        />
      ))}
    </div>
  );
}

function TaxonomyRow({ entry, depth = 0, hasChildren, expanded, onToggleExpand, onToggle }: {
  entry: IABEntry; depth?: number; hasChildren?: boolean; expanded?: boolean;
  onToggleExpand?: () => void; onToggle: () => void;
}) {
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 8,
      padding: "4px 8px", paddingLeft: 8 + depth * 20,
      borderBottom: "1px solid var(--border)", fontSize: 12,
    }}>
      {hasChildren ? (
        <button className="btn btn-sm btn-icon" onClick={onToggleExpand} style={{ fontSize: 10 }}>
          {expanded ? "▾" : "▸"}
        </button>
      ) : <span style={{ width: 20 }} />}
      <span style={{ color: "var(--fg-mute)", fontFamily: "monospace", minWidth: 40 }}>{entry.unique_id}</span>
      <span style={{ flex: 1 }}>{entry.name}</span>
      {entry.tier_2 && <span style={{ color: "var(--fg-mute)", fontSize: 10 }}>{entry.tier_1} › {entry.tier_2}</span>}
      <button
        className={cn("btn btn-sm", entry.active ? "" : "btn-primary")}
        style={{ fontSize: 10 }}
        onClick={onToggle}
        title={entry.active ? "Deactivate" : "Activate"}
      >
        {entry.active ? "Active" : "Inactive"}
      </button>
    </div>
  );
}

// ── Brand Rules Tab ─────────────────────────────────────────

function BrandRulesTab() {
  const [rules, setRules] = useState<BrandRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [newBrand, setNewBrand] = useState("");
  const [newCategory, setNewCategory] = useState("");
  const [newIabId, setNewIabId] = useState("");

  const load = useCallback(() => {
    setLoading(true);
    knowledgeApi.listBrandRules(false).then(setRules).finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const add = async () => {
    if (!newBrand.trim()) return;
    await knowledgeApi.createBrandRule({
      brand_name: newBrand.trim(),
      primary_category: newCategory.trim() || null,
      iab_product_id: newIabId.trim() || null,
      source: "manual",
    });
    setNewBrand(""); setNewCategory(""); setNewIabId("");
    load();
  };

  const remove = async (id: number) => {
    await knowledgeApi.deleteBrandRule(id);
    load();
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div className="dcard">
        <div className="dcard-head"><span>Add Brand Rule</span></div>
        <div style={{ display: "flex", gap: 8, padding: 8 }}>
          <input className="input" style={{ flex: 2 }} placeholder="Brand name" value={newBrand} onChange={e => setNewBrand(e.target.value)} />
          <input className="input" style={{ flex: 2 }} placeholder="Primary category" value={newCategory} onChange={e => setNewCategory(e.target.value)} />
          <input className="input" style={{ flex: 1 }} placeholder="IAB product ID" value={newIabId} onChange={e => setNewIabId(e.target.value)} />
          <button className="btn btn-primary" onClick={add}>Add</button>
        </div>
      </div>

      {loading ? <div style={{ color: "var(--fg-mute)" }}>Loading...</div> : (
        <div className="dcard">
          <div className="dcard-head"><span>Brand Rules ({rules.length})</span></div>
          <table style={{ width: "100%", fontSize: 12 }}>
            <thead>
              <tr><th>Brand</th><th>Category</th><th>IAB Product</th><th>Source</th><th>Confidence</th><th>Active</th><th></th></tr>
            </thead>
            <tbody>
              {rules.map(r => (
                <tr key={r.id}>
                  <td style={{ fontWeight: 500 }}>{r.brand_name}</td>
                  <td>{r.primary_category ?? "—"}</td>
                  <td style={{ fontFamily: "monospace" }}>{r.iab_product_id ?? "—"}</td>
                  <td><span style={{ fontSize: 10, color: "var(--fg-mute)" }}>{r.source}</span></td>
                  <td>{r.confidence.toFixed(2)}</td>
                  <td>{r.active ? "✓" : "—"}</td>
                  <td><button className="btn btn-sm" onClick={() => remove(r.id)}>✕</button></td>
                </tr>
              ))}
              {rules.length === 0 && <tr><td colSpan={7} style={{ color: "var(--fg-mute)" }}>No brand rules yet</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Overrides Tab ───────────────────────────────────────────

function OverridesTab() {
  const [overrides, setOverrides] = useState<Override[]>([]);
  const [loading, setLoading] = useState(true);
  const [newType, setNewType] = useState("keyword");
  const [newPattern, setNewPattern] = useState("");
  const [newCategory, setNewCategory] = useState("");
  const [newIabId, setNewIabId] = useState("");

  const load = useCallback(() => {
    setLoading(true);
    knowledgeApi.listOverrides().then(setOverrides).finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const add = async () => {
    if (!newPattern.trim()) return;
    await knowledgeApi.createOverride({
      override_type: newType,
      pattern: newPattern.trim(),
      primary_category: newCategory.trim() || null,
      iab_product_id: newIabId.trim() || null,
    });
    setNewPattern(""); setNewCategory(""); setNewIabId("");
    load();
  };

  const remove = async (id: number) => {
    await knowledgeApi.deleteOverride(id);
    load();
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div className="dcard">
        <div className="dcard-head"><span>Add Override</span></div>
        <div style={{ display: "flex", gap: 8, padding: 8 }}>
          <select className="input" style={{ flex: 1 }} value={newType} onChange={e => setNewType(e.target.value)}>
            <option value="brand">Brand</option>
            <option value="keyword">Keyword</option>
            <option value="subcategory">Subcategory</option>
            <option value="product_text">Product Text</option>
          </select>
          <input className="input" style={{ flex: 2 }} placeholder="Pattern" value={newPattern} onChange={e => setNewPattern(e.target.value)} />
          <input className="input" style={{ flex: 2 }} placeholder="Primary category" value={newCategory} onChange={e => setNewCategory(e.target.value)} />
          <input className="input" style={{ flex: 1 }} placeholder="IAB product ID" value={newIabId} onChange={e => setNewIabId(e.target.value)} />
          <button className="btn btn-primary" onClick={add}>Add</button>
        </div>
      </div>

      {loading ? <div style={{ color: "var(--fg-mute)" }}>Loading...</div> : (
        <div className="dcard">
          <div className="dcard-head"><span>Overrides ({overrides.length})</span></div>
          <table style={{ width: "100%", fontSize: 12 }}>
            <thead>
              <tr><th>Type</th><th>Pattern</th><th>Category</th><th>IAB Product</th><th>Active</th><th></th></tr>
            </thead>
            <tbody>
              {overrides.map(o => (
                <tr key={o.id}>
                  <td><span style={{ fontSize: 10, color: "var(--fg-mute)" }}>{o.override_type}</span></td>
                  <td style={{ fontWeight: 500 }}>{o.pattern}</td>
                  <td>{o.primary_category ?? "—"}</td>
                  <td style={{ fontFamily: "monospace" }}>{o.iab_product_id ?? "—"}</td>
                  <td>{o.active ? "✓" : "—"}</td>
                  <td><button className="btn btn-sm" onClick={() => remove(o.id)}>✕</button></td>
                </tr>
              ))}
              {overrides.length === 0 && <tr><td colSpan={6} style={{ color: "var(--fg-mute)" }}>No overrides yet</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Inference Rules Tab ─────────────────────────────────────

function InferenceRulesTab() {
  const [rules, setRules] = useState<InferenceRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [newType, setNewType] = useState("content");
  const [newTarget, setNewTarget] = useState("");
  const [newTerms, setNewTerms] = useState("");

  const load = useCallback(() => {
    setLoading(true);
    knowledgeApi.listInferenceRules().then(setRules).finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const add = async () => {
    if (!newTarget.trim() || !newTerms.trim()) return;
    await knowledgeApi.createInferenceRule({
      taxonomy_type: newType,
      target_id: newTarget.trim(),
      terms: newTerms.split(",").map(t => t.trim()).filter(Boolean),
    });
    setNewTarget(""); setNewTerms("");
    load();
  };

  const remove = async (id: number) => {
    await knowledgeApi.deleteInferenceRule(id);
    load();
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div className="dcard">
        <div className="dcard-head"><span>Add Inference Rule</span></div>
        <div style={{ display: "flex", gap: 8, padding: 8 }}>
          <select className="input" style={{ flex: 1 }} value={newType} onChange={e => setNewType(e.target.value)}>
            <option value="content">Content</option>
            <option value="product">Product</option>
          </select>
          <input className="input" style={{ flex: 1 }} placeholder="Target IAB ID" value={newTarget} onChange={e => setNewTarget(e.target.value)} />
          <input className="input" style={{ flex: 3 }} placeholder="Terms (comma-separated)" value={newTerms} onChange={e => setNewTerms(e.target.value)} />
          <button className="btn btn-primary" onClick={add}>Add</button>
        </div>
      </div>

      {loading ? <div style={{ color: "var(--fg-mute)" }}>Loading...</div> : (
        <div className="dcard">
          <div className="dcard-head"><span>Inference Rules ({rules.length})</span></div>
          <table style={{ width: "100%", fontSize: 12 }}>
            <thead>
              <tr><th>Type</th><th>Target</th><th>Terms</th><th>Context</th><th>Notes</th><th></th></tr>
            </thead>
            <tbody>
              {rules.map(r => (
                <tr key={r.id}>
                  <td><span style={{ fontSize: 10, color: "var(--fg-mute)" }}>{r.taxonomy_type}</span></td>
                  <td style={{ fontFamily: "monospace" }}>{r.target_id}</td>
                  <td style={{ maxWidth: 300, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.terms.join(", ")}</td>
                  <td style={{ maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.context_terms.join(", ") || "—"}</td>
                  <td style={{ color: "var(--fg-mute)", fontSize: 10 }}>{r.notes ?? "—"}</td>
                  <td><button className="btn btn-sm" onClick={() => remove(r.id)}>✕</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Backfill Tab ────────────────────────────────────────────

function BackfillTab() {
  const [suggestions, setSuggestions] = useState<BackfillSuggestion[]>([]);
  const [loading, setLoading] = useState(false);
  const [applied, setApplied] = useState<Set<string>>(new Set());

  const analyze = async () => {
    setLoading(true);
    try {
      const results = await knowledgeApi.analyzeBackfill(true, 1000);
      setSuggestions(results);
    } catch (e) {
      alert("Analysis failed: " + (e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const apply = async (s: BackfillSuggestion) => {
    try {
      await knowledgeApi.applyBackfill(s);
      setApplied(prev => new Set(prev).add(s.ad_id));
    } catch (e) {
      alert("Apply failed: " + (e as Error).message);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <button className="btn btn-primary" disabled={loading} onClick={analyze}>
          {loading ? "Analyzing..." : "Run Backfill Analysis"}
        </button>
        <span style={{ color: "var(--fg-mute)", fontSize: 12 }}>
          Compare existing ads against current knowledge base rules
        </span>
      </div>

      {suggestions.length > 0 && (
        <div className="dcard">
          <div className="dcard-head"><span>Suggestions ({suggestions.length})</span></div>
          <table style={{ width: "100%", fontSize: 12 }}>
            <thead>
              <tr>
                <th>Ad ID</th>
                <th>Brand</th>
                <th>Current</th>
                <th>Suggested</th>
                <th>Rule</th>
                <th>Conf.</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {suggestions.map(s => (
                <tr key={s.ad_id} style={{ opacity: applied.has(s.ad_id) ? 0.4 : 1 }}>
                  <td style={{ fontFamily: "monospace", fontSize: 10 }}>{s.ad_id.slice(0, 12)}</td>
                  <td>{s.brand_name ?? "—"}</td>
                  <td>
                    <div>{s.current_primary_category ?? "—"}</div>
                    {s.current_iab_product_id && (
                      <div style={{ fontSize: 10, color: "var(--fg-mute)" }}>IAB: {s.current_iab_product_id}</div>
                    )}
                  </td>
                  <td>
                    <div style={{ fontWeight: 500 }}>{s.suggested_primary_category ?? "—"}</div>
                    {s.suggested_iab_product_id && (
                      <div style={{ fontSize: 10, color: "var(--accent-2)" }}>IAB: {s.suggested_iab_product_id}</div>
                    )}
                  </td>
                  <td style={{ fontSize: 10, color: "var(--fg-mute)" }}>{s.rule_source ?? "—"}</td>
                  <td>{s.confidence.toFixed(2)}</td>
                  <td>
                    {applied.has(s.ad_id) ? (
                      <span style={{ color: "var(--accent-2)", fontSize: 10 }}>Applied</span>
                    ) : (
                      <button className="btn btn-sm btn-primary" onClick={() => apply(s)}>Apply</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
