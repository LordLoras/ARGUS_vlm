import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  Archive,
  Box,
  Boxes,
  ChevronRight,
  CirclePlay,
  Database,
  ExternalLink,
  FileImage,
  Film,
  Image,
  Link as LinkIcon,
  Plus,
  Radio,
  Search,
  Trash2,
  ToggleLeft,
  ToggleRight
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { ApiOfflineBanner } from "../components/shared/ApiOfflineBanner";
import { EmptyState } from "../components/shared/EmptyState";
import { Topbar } from "../components/Topbar";
import { useApiHealth } from "../hooks/useApiHealth";
import { api } from "../lib/api-client";
import type {
  IntelAdapterDescriptor,
  IntelArtifactSummary,
  IntelBrandOverview,
  IntelCrawlSummary,
  IntelResource,
  IntelResourceArtifact,
  IntelSignal,
  IntelSource,
  IntelTier
} from "../lib/intel-types";
import "./Watcher.css";

const FALLBACK_ADAPTERS: IntelAdapterDescriptor[] = [
  {
    source_type: "meta_ad_library_ui",
    label: "Meta Ad Library",
    target_label: "Meta advertiser Page ID",
    target_placeholder: "Toyota Facebook Page ID, e.g. 197052454200",
    helper_text:
      "Public Meta Ad Library monitoring for a Facebook advertiser Page ID, not a single ad or campaign id. " +
      "Stores visible cards, screenshots, copy, image URLs, exposed video URLs, and multiple-version counts when shown.",
    default_tier: "B",
    platform: "meta",
    requires_url: false,
    requires_platform_id: true,
    config: {
      active_status: "active",
      sort_mode: "relevancy_monthly_grouped",
      sort_direction: "desc",
      scrolls: 20,
      max_cards: 250,
      wait_ms: 1800,
      stop_after_no_new: 3
    },
    provides: [
      "Meta library IDs",
      "card screenshots",
      "visible ad copy",
      "image URLs",
      "video URLs when exposed",
      "multiple-version counts"
    ]
  },
  {
    source_type: "youtube_channel",
    label: "YouTube channel",
    target_label: "Channel ID",
    target_placeholder: "UC...",
    helper_text: "Official channel monitoring through public feeds and video metadata.",
    default_tier: "A",
    platform: "youtube",
    requires_url: false,
    requires_platform_id: true,
    config: {},
    provides: ["video ids", "titles", "descriptions", "publish dates", "thumbnails"]
  },
  {
    source_type: "rss",
    label: "RSS / newsroom feed",
    target_label: "Feed URL",
    target_placeholder: "https://pressroom.toyota.com/product/feed/",
    helper_text: "Robots-gated feed monitoring for newsroom and trade-press releases.",
    default_tier: "A",
    platform: null,
    requires_url: true,
    requires_platform_id: false,
    config: {},
    provides: ["article URLs", "titles", "descriptions", "publish dates"]
  }
];

const META_SORT_OPTIONS = [
  { value: "relevancy_monthly_grouped", label: "Meta default" },
  { value: "total_impressions", label: "Highest impressions" }
] as const;

const RESOURCE_SORT_OPTIONS = [
  { value: "newest", label: "Newest first" },
  { value: "versions", label: "Most versions" },
  { value: "videos", label: "Video first" },
  { value: "artifacts", label: "Most artifacts" }
] as const;

type ResourceSort = (typeof RESOURCE_SORT_OPTIONS)[number]["value"];

function adapterLabel(sourceType: string, adapters: IntelAdapterDescriptor[]) {
  return adapters.find((adapter) => adapter.source_type === sourceType)?.label ?? sourceType.replace(/_/g, " ");
}

function sourceTarget(source: IntelSource) {
  return source.url || source.platform_id || "No target configured";
}

function sourceStateLabel(source: IntelSource) {
  return source.source_activated_at ? "activated" : "baseline pending";
}

function artifactTotal(summary: IntelArtifactSummary) {
  return (
    summary.screenshot_count +
    summary.image_source_count +
    summary.video_source_count +
    summary.video_poster_count +
    summary.background_image_source_count +
    summary.link_count +
    summary.media_asset_count
  );
}

function formatConfidence(value: number) {
  return `${Math.round(value * 100)}%`;
}

export function Watcher() {
  const health = useApiHealth();
  const queryClient = useQueryClient();

  const [brandSearch, setBrandSearch] = useState("");
  const [selectedBrand, setSelectedBrand] = useState<string | null>(null);
  const [brand, setBrand] = useState("");
  const [sourceType, setSourceType] = useState("meta_ad_library_ui");
  const [url, setUrl] = useState("");
  const [platformId, setPlatformId] = useState("");
  const [tier, setTier] = useState<IntelTier>("B");
  const [enabled, setEnabled] = useState(true);
  const [metaSortMode, setMetaSortMode] = useState("relevancy_monthly_grouped");
  const [resourceSort, setResourceSort] = useState<ResourceSort>("newest");
  const [error, setError] = useState<string | null>(null);
  const [lastRun, setLastRun] = useState<IntelCrawlSummary | null>(null);

  const adaptersQuery = useQuery({
    queryKey: ["intel-adapters"],
    queryFn: () => api.listIntelAdapters()
  });
  const brandsQuery = useQuery({
    queryKey: ["intel-brands", brandSearch],
    queryFn: () => api.listIntelBrands({ q: brandSearch.trim() || undefined, limit: 100 })
  });
  const sourcesQuery = useQuery({
    queryKey: ["intel-sources"],
    queryFn: () => api.listIntelSources()
  });
  const signalsQuery = useQuery({
    queryKey: ["intel-signals"],
    queryFn: () => api.listIntelSignals({ limit: 100 })
  });
  const resourcesQuery = useQuery({
    queryKey: ["intel-resources", selectedBrand],
    queryFn: () => api.listIntelResources({ brand: selectedBrand ?? undefined, limit: 40 }),
    enabled: Boolean(selectedBrand)
  });

  const adapters = adaptersQuery.data?.items?.length ? adaptersQuery.data.items : FALLBACK_ADAPTERS;
  const selectedAdapter =
    adapters.find((adapter) => adapter.source_type === sourceType) ?? adapters[0] ?? FALLBACK_ADAPTERS[0];
  const brands = brandsQuery.data?.items ?? [];
  const sources = sourcesQuery.data?.items ?? [];
  const signals = signalsQuery.data?.items ?? [];
  const resources = resourcesQuery.data?.items ?? [];
  const sortedResources = useMemo(
    () => sortResources(resources, resourceSort),
    [resources, resourceSort]
  );
  const selectedBrandOverview = brands.find((item) => item.brand_name === selectedBrand) ?? null;
  const selectedSources = sources.filter((source) => source.brand_name === selectedBrand);
  const selectedSignals = signals.filter((signal) => signal.brand_name === selectedBrand);
  const enabledCount = sources.filter((source) => source.enabled).length;
  const totalResources = brands.reduce((sum, item) => sum + item.resource_count, 0);

  const sourceTypeOptions = useMemo(
    () => adapters.map((adapter) => adapter.source_type),
    [adapters]
  );

  useEffect(() => {
    if (!selectedBrand && brands.length > 0) {
      setSelectedBrand(brands[0].brand_name);
    }
  }, [brands, selectedBrand]);

  useEffect(() => {
    if (selectedBrand && !brand) {
      setBrand(selectedBrand);
    }
  }, [brand, selectedBrand]);

  useEffect(() => {
    if (sourceTypeOptions.length > 0 && !sourceTypeOptions.includes(sourceType)) {
      setSourceType(sourceTypeOptions[0]);
    }
  }, [sourceType, sourceTypeOptions]);

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["intel-brands"] });
    void queryClient.invalidateQueries({ queryKey: ["intel-sources"] });
    void queryClient.invalidateQueries({ queryKey: ["intel-signals"] });
    void queryClient.invalidateQueries({ queryKey: ["intel-resources"] });
  };

  const createMutation = useMutation({
    mutationFn: () =>
      api.createIntelSource({
        brand: brand.trim(),
        source_type: selectedAdapter.source_type,
        tier,
        url: url.trim() || null,
        platform: selectedAdapter.platform ?? platformForSourceType(selectedAdapter.source_type),
        platform_id: platformId.trim() || null,
        enabled,
        config: buildSourceConfig(selectedAdapter, metaSortMode)
      }),
    onSuccess: (source) => {
      setError(null);
      setSelectedBrand(source.brand_name);
      setBrand(source.brand_name);
      setUrl("");
      setPlatformId("");
      invalidate();
    },
    onError: (err) => setError(errorMessage(err))
  });

  const toggleMutation = useMutation({
    mutationFn: (source: IntelSource) => api.updateIntelSource(source.id, { enabled: !source.enabled }),
    onSuccess: invalidate,
    onError: (err) => setError(errorMessage(err))
  });
  const deleteMutation = useMutation({
    mutationFn: (sourceId: string) => api.deleteIntelSource(sourceId),
    onSuccess: invalidate,
    onError: (err) => setError(errorMessage(err))
  });
  const crawlSourceMutation = useMutation({
    mutationFn: (sourceId: string) => api.crawlIntelSource(sourceId),
    onSuccess: (summary) => {
      setError(null);
      setLastRun(summary);
      invalidate();
    },
    onError: (err) => setError(errorMessage(err))
  });
  const crawlBrandMutation = useMutation({
    mutationFn: (brandName: string) => api.runIntelCrawl({ due: true, brand: brandName }),
    onSuccess: (summary) => {
      setError(null);
      setLastRun(summary);
      invalidate();
    },
    onError: (err) => setError(errorMessage(err))
  });

  const crawlBusy = crawlBrandMutation.isPending || crawlSourceMutation.isPending;
  const runningSourceId = crawlSourceMutation.isPending ? crawlSourceMutation.variables : null;

  const onSourceTypeChange = (nextSourceType: string) => {
    const nextAdapter = adapters.find((adapter) => adapter.source_type === nextSourceType);
    setSourceType(nextSourceType);
    setTier(nextAdapter?.default_tier ?? "B");
    setMetaSortMode(String(nextAdapter?.config?.sort_mode ?? "relevancy_monthly_grouped"));
    setUrl("");
    setPlatformId("");
  };

  const onSelectBrand = (nextBrand: string) => {
    setSelectedBrand(nextBrand);
    setBrand(nextBrand);
  };

  const targetMissing =
    (selectedAdapter.requires_platform_id && !platformId.trim()) ||
    (selectedAdapter.requires_url && !url.trim());
  const canCreateSource = Boolean(brand.trim()) && !targetMissing && !createMutation.isPending;

  return (
    <>
      <Topbar crumbs={["Experimental", "Watcher"]} />
      <ApiOfflineBanner offline={health.isError} />

      <div className="page watcher-page">
        <section className="watcher-hero">
          <div className="watcher-hero-copy">
            <span className="watcher-kicker">Brand intelligence</span>
            <h1 className="page-title">Watcher</h1>
            <p className="page-sub">
              Monitor brands through adapter-backed sources, inspect what each adapter captured,
              and separate baseline backfill from live campaign signals.
            </p>
          </div>
          <div className="watcher-metrics">
            <Metric label="Brands" value={brands.length} />
            <Metric label="Sources" value={`${enabledCount}/${sources.length}`} />
            <Metric label="Resources" value={totalResources} />
            <Metric label="Signals" value={signals.length} />
          </div>
        </section>

        <section className="watcher-panel watcher-toolbar">
          <label className="watcher-search-field">
            <Search size={15} />
            <input
              value={brandSearch}
              onChange={(event) => setBrandSearch(event.target.value)}
              placeholder="Search monitored brands"
            />
          </label>
          <button
            className="watcher-secondary-action"
            disabled={!selectedBrand || crawlBusy}
            onClick={() => selectedBrand && crawlBrandMutation.mutate(selectedBrand)}
          >
            <CirclePlay size={14} />
            <span>{crawlBrandMutation.isPending ? "Running brand" : "Run selected brand"}</span>
          </button>
        </section>

        <div className="watcher-brand-layout">
          <section className="watcher-panel">
            <div className="watcher-panel-header">
              <div>
                <span className="watcher-section-kicker">Brands</span>
                <h2>Coverage map</h2>
              </div>
            </div>
            {brandsQuery.isLoading ? (
              <div className="watcher-muted-line">Loading brands...</div>
            ) : brands.length === 0 ? (
              <EmptyState
                icon={<Search size={18} />}
                title="No monitored brands"
                hint="Add the first source for a brand to create its Watcher profile."
              />
            ) : (
              <div className="watcher-brand-grid">
                {brands.map((item) => (
                  <BrandCard
                    adapters={adapters}
                    brand={item}
                    isSelected={item.brand_name === selectedBrand}
                    key={item.brand_name}
                    onSelect={() => onSelectBrand(item.brand_name)}
                  />
                ))}
              </div>
            )}
          </section>

          <section className="watcher-panel watcher-brand-detail">
            <div className="watcher-detail-header">
              <div>
                <span className="watcher-section-kicker">Selected brand</span>
                <h2>{selectedBrand ?? "Choose a brand"}</h2>
              </div>
              {selectedBrandOverview ? (
                <div className="watcher-detail-stats">
                  <Metric label="Resources" value={selectedBrandOverview.resource_count} />
                  <Metric label="Artifacts" value={artifactTotal(selectedBrandOverview.artifact_summary)} />
                  <Metric label="Signals" value={selectedBrandOverview.signal_count} />
                </div>
              ) : null}
            </div>

            <section className="watcher-split-panel">
              <div>
                <span className="watcher-section-kicker">Add adapter</span>
                <h3>Attach a source</h3>
              </div>
              <div className="watcher-form-grid">
                <label className="watcher-field">
                  <span>Brand</span>
                  <input
                    className="input"
                    value={brand}
                    onChange={(event) => setBrand(event.target.value)}
                    placeholder="Toyota"
                  />
                </label>
                <label className="watcher-field">
                  <span>Adapter</span>
                  <select
                    className="input"
                    value={sourceType}
                    onChange={(event) => onSourceTypeChange(event.target.value)}
                  >
                    {sourceTypeOptions.map((type) => (
                      <option key={type} value={type}>
                        {adapterLabel(type, adapters)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="watcher-field">
                  <span>Tier</span>
                  <select
                    className="input"
                    value={tier}
                    onChange={(event) => setTier(event.target.value as IntelTier)}
                  >
                    <option value="A">A - strong</option>
                    <option value="B">B - medium</option>
                    <option value="C">C - corroboration</option>
                  </select>
                </label>
                <label className="watcher-field watcher-wide-field">
                  <span>{selectedAdapter.target_label}</span>
                  <input
                    className="input"
                    value={selectedAdapter.requires_url ? url : platformId}
                    onChange={(event) =>
                      selectedAdapter.requires_url
                        ? setUrl(event.target.value)
                        : setPlatformId(event.target.value)
                    }
                    placeholder={selectedAdapter.target_placeholder}
                  />
                </label>
                {!selectedAdapter.requires_url ? (
                  <label className="watcher-field">
                    <span>URL override</span>
                    <input
                      className="input"
                      value={url}
                      onChange={(event) => setUrl(event.target.value)}
                      placeholder="Optional adapter URL"
                    />
                  </label>
                ) : null}
                {selectedAdapter.source_type === "meta_ad_library_ui" ? (
                  <label className="watcher-field">
                    <span>Meta sort</span>
                    <select
                      className="input"
                      value={metaSortMode}
                      onChange={(event) => setMetaSortMode(event.target.value)}
                    >
                      {META_SORT_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : null}
                <label className="watcher-toggle">
                  <input
                    type="checkbox"
                    checked={enabled}
                    onChange={(event) => setEnabled(event.target.checked)}
                    aria-label="Enabled"
                  />
                  <span className="watcher-switch" aria-hidden="true" />
                  <span>Enabled</span>
                </label>
                <div className="watcher-form-actions">
                  <button
                    className="watcher-primary-action"
                    disabled={!canCreateSource}
                    onClick={() => createMutation.mutate()}
                  >
                    <Plus size={14} />
                    <span>{createMutation.isPending ? "Adding" : "Add source"}</span>
                  </button>
                </div>
              </div>
              <AdapterCapability adapter={selectedAdapter} />
              {error ? <div className="watcher-error">{error}</div> : null}
              {lastRun ? (
                <div className="watcher-run-summary">
                  <Metric label="Status" value={lastRun.status} />
                  <Metric label="Sources" value={lastRun.source_count} />
                  <Metric label="New resources" value={lastRun.resource_count} />
                  <Metric label="New signals" value={lastRun.signal_count} />
                </div>
              ) : null}
            </section>

            <section className="watcher-split-panel">
              <div className="watcher-panel-header">
                <div>
                  <span className="watcher-section-kicker">Adapters</span>
                  <h3>Sources for {selectedBrand ?? "brand"}</h3>
                </div>
              </div>
              {selectedBrand && selectedSources.length === 0 ? (
                <EmptyState
                  icon={<Database size={18} />}
                  title="No sources for this brand"
                  hint="Attach Meta, YouTube, RSS, or another adapter to start collecting resources."
                />
              ) : (
                <div className="watcher-source-list">
                  {selectedSources.map((source) => (
                    <SourceRow
                      adapters={adapters}
                      crawlBusy={crawlBusy}
                      isRunning={runningSourceId === source.id}
                      key={source.id}
                      onDelete={() => deleteMutation.mutate(source.id)}
                      onRun={() => crawlSourceMutation.mutate(source.id)}
                      onToggle={() => toggleMutation.mutate(source)}
                      source={source}
                    />
                  ))}
                </div>
              )}
            </section>

            <section className="watcher-split-panel">
              <div className="watcher-panel-header">
                <div>
                  <span className="watcher-section-kicker">Artifacts</span>
                  <h3>Resources captured</h3>
                </div>
                <div className="watcher-resource-controls">
                  <span className="watcher-muted-line">
                    {resources.length ? `${resources.length} captured` : ""}
                  </span>
                  <select
                    className="input watcher-compact-select"
                    value={resourceSort}
                    onChange={(event) => setResourceSort(event.target.value as ResourceSort)}
                  >
                    {RESOURCE_SORT_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              {resourcesQuery.isLoading ? (
                <div className="watcher-muted-line">Loading resources...</div>
              ) : !selectedBrand || resources.length === 0 ? (
                <EmptyState
                  icon={<Archive size={18} />}
                  title="No resources yet"
                  hint="Run an adapter to backfill observed ads and source artifacts."
                />
              ) : (
                <div className="watcher-resource-list">
                  {sortedResources.map((resource) => (
                    <ResourceCard
                      adapters={adapters}
                      key={resource.id}
                      resource={resource}
                    />
                  ))}
                </div>
              )}
            </section>

            <section className="watcher-split-panel">
              <div className="watcher-panel-header">
                <div>
                  <span className="watcher-section-kicker">Signals</span>
                  <h3>Live campaign activity</h3>
                </div>
              </div>
              {selectedSignals.length === 0 ? (
                <EmptyState
                  icon={<AlertTriangle size={18} />}
                  title="No live signals for this brand"
                  hint="Baseline resources are stored first; new post-activation items become signals."
                />
              ) : (
                <div className="watcher-signal-list">
                  {selectedSignals.map((signal) => (
                    <SignalCard key={signal.id} signal={signal} />
                  ))}
                </div>
              )}
            </section>
          </section>
        </div>
      </div>
    </>
  );
}

function BrandCard({
  adapters,
  brand,
  isSelected,
  onSelect
}: {
  adapters: IntelAdapterDescriptor[];
  brand: IntelBrandOverview;
  isSelected: boolean;
  onSelect: () => void;
}) {
  return (
    <button className={`watcher-brand-card ${isSelected ? "is-selected" : ""}`} onClick={onSelect}>
      <div className="watcher-brand-card-top">
        <div>
          <strong>{brand.brand_name}</strong>
          <span>{brand.source_types.map((type) => adapterLabel(type, adapters)).join(", ") || "No adapters"}</span>
        </div>
        <ChevronRight size={16} />
      </div>
      <div className="watcher-brand-stats">
        <span>{brand.enabled_source_count}/{brand.source_count} sources</span>
        <span>{brand.resource_count} resources</span>
        <span>{artifactTotal(brand.artifact_summary)} artifacts</span>
        <span>{brand.signal_count} signals</span>
      </div>
    </button>
  );
}

function AdapterCapability({ adapter }: { adapter: IntelAdapterDescriptor }) {
  return (
    <div className="watcher-adapter-card">
      <div>
        <strong>{adapter.label}</strong>
        <span>{adapter.helper_text}</span>
      </div>
      <div className="watcher-provider-chips">
        {adapter.provides.map((item) => (
          <span key={item}>{item}</span>
        ))}
      </div>
    </div>
  );
}

function SourceRow({
  adapters,
  crawlBusy,
  isRunning,
  onDelete,
  onRun,
  onToggle,
  source
}: {
  adapters: IntelAdapterDescriptor[];
  crawlBusy: boolean;
  isRunning: boolean;
  onDelete: () => void;
  onRun: () => void;
  onToggle: () => void;
  source: IntelSource;
}) {
  return (
    <article className={`watcher-source-row ${source.enabled ? "is-enabled" : ""}`}>
      <div>
        <strong>{adapterLabel(source.source_type, adapters)}</strong>
        <span>{sourceTarget(source)}</span>
      </div>
      <div className="watcher-source-tags">
        <span>Tier {source.tier}</span>
        <span>{sourceStateLabel(source)}</span>
        <span>{source.enabled ? "enabled" : "disabled"}</span>
      </div>
      <div className="watcher-source-actions">
        <button className="watcher-card-action" disabled={crawlBusy} onClick={onRun}>
          <CirclePlay size={14} />
          <span>{isRunning ? "Running" : "Run"}</span>
        </button>
        <button className="watcher-card-action" onClick={onToggle}>
          {source.enabled ? <ToggleLeft size={14} /> : <ToggleRight size={14} />}
          <span>{source.enabled ? "Disable" : "Enable"}</span>
        </button>
        <button className="watcher-card-action danger" onClick={onDelete}>
          <Trash2 size={14} />
          <span>Delete</span>
        </button>
      </div>
    </article>
  );
}

function ResourceCard({
  adapters,
  resource
}: {
  adapters: IntelAdapterDescriptor[];
  resource: IntelResource;
}) {
  const title = resourceTitle(resource);
  const copy = resourceCopy(resource);
  const facts = resourceFacts(resource);
  const hiddenArtifacts = Math.max(0, resource.artifacts.length - 8);

  return (
    <article className="watcher-resource-card">
      <div className="watcher-resource-head">
        <div>
          <strong>{title}</strong>
          <span>
            {adapterLabel(resource.source_type, adapters)} · {resource.resource_type} ·{" "}
            {formatDate(resource.published_at || resource.first_seen_at)}
          </span>
        </div>
        <div className="watcher-resource-pills">
          {resourceHasVariants(resource) ? (
            <span className="watcher-state-pill versions">{variantsLabel(resource)}</span>
          ) : null}
          <span className={`watcher-state-pill ${resource.is_backfill ? "disabled" : "enabled"}`}>
            {resource.is_backfill ? "backfill" : "live"}
          </span>
        </div>
      </div>
      {facts.length > 0 ? (
        <div className="watcher-resource-meta">
          {facts.map((fact) => (
            <span key={`${fact.label}-${fact.value}`}>
              {fact.label}: {fact.value}
            </span>
          ))}
        </div>
      ) : null}
      {copy ? <p className="watcher-resource-copy">{copy}</p> : null}
      <ArtifactSummary summary={resource.artifact_summary} />
      <div className="watcher-artifact-strip">
        {resource.artifacts.slice(0, 8).map((artifact, index) => (
          <ArtifactLink artifact={artifact} key={`${artifact.artifact_type}-${index}`} />
        ))}
        {hiddenArtifacts > 0 ? (
          <span className="watcher-artifact-link">+{hiddenArtifacts} more</span>
        ) : null}
      </div>
    </article>
  );
}

function ArtifactSummary({ summary }: { summary: IntelArtifactSummary }) {
  const chips = [
    { icon: <FileImage size={12} />, label: "screens", value: summary.screenshot_count },
    { icon: <Image size={12} />, label: "images", value: summary.image_source_count },
    { icon: <Film size={12} />, label: "videos", value: summary.video_source_count },
    { icon: <LinkIcon size={12} />, label: "links", value: summary.link_count },
    { icon: <Boxes size={12} />, label: "assets", value: summary.media_asset_count }
  ].filter((item) => item.value > 0);
  if (chips.length === 0) {
    return <span className="watcher-muted-line">No artifacts extracted</span>;
  }
  return (
    <div className="watcher-artifact-summary">
      {chips.map((item) => (
        <span key={item.label}>
          {item.icon}
          {item.value} {item.label}
        </span>
      ))}
    </div>
  );
}

function ArtifactLink({ artifact }: { artifact: IntelResourceArtifact }) {
  const icon = artifact.artifact_type.includes("video") ? (
    <Film size={12} />
  ) : artifact.artifact_type.includes("link") ? (
    <LinkIcon size={12} />
  ) : artifact.artifact_type.includes("screenshot") ? (
    <FileImage size={12} />
  ) : (
    <Box size={12} />
  );
  const label = artifact.label || artifact.artifact_type;
  if (artifact.url) {
    return (
      <a className="watcher-artifact-link" href={artifact.url} target="_blank" rel="noreferrer">
        {icon}
        <span>{label}</span>
        <ExternalLink size={11} />
      </a>
    );
  }
  return (
    <span className="watcher-artifact-link">
      {icon}
      <span>{label}</span>
    </span>
  );
}

function SignalCard({ signal }: { signal: IntelSignal }) {
  return (
    <article className="watcher-signal-card">
      <div className="watcher-signal-icon">
        <Radio size={16} />
      </div>
      <div className="watcher-signal-main">
        <div className="watcher-signal-title">
          <strong>{signal.campaign_name || signal.title}</strong>
          <span>{signal.brand_name}</span>
        </div>
        <div className="watcher-source-tags">
          <span>{signal.signal_type}</span>
          <span>{signal.status}</span>
          <span>{formatConfidence(signal.confidence)}</span>
          {signal.source_published_at ? <span>{formatDate(signal.source_published_at)}</span> : null}
        </div>
      </div>
      {signal.evidence[0]?.url ? (
        <a
          className="watcher-card-action"
          href={signal.evidence[0].url}
          target="_blank"
          rel="noreferrer"
        >
          <ExternalLink size={14} />
          <span>Open</span>
        </a>
      ) : (
        <span className="watcher-muted-line">No evidence URL</span>
      )}
    </article>
  );
}

function buildSourceConfig(adapter: IntelAdapterDescriptor, metaSortMode: string) {
  if (adapter.source_type !== "meta_ad_library_ui") {
    return adapter.config;
  }
  return {
    ...adapter.config,
    sort_mode: metaSortMode,
    sort_direction: "desc"
  };
}

function sortResources(resources: IntelResource[], sort: ResourceSort) {
  const copy = [...resources];
  const byNewest = (resource: IntelResource) =>
    Date.parse(resource.published_at || resource.first_seen_at || "") || 0;
  copy.sort((left, right) => {
    if (sort === "versions") {
      return metaVariantCount(right) - metaVariantCount(left) || byNewest(right) - byNewest(left);
    }
    if (sort === "videos") {
      return videoTotal(right) - videoTotal(left) || byNewest(right) - byNewest(left);
    }
    if (sort === "artifacts") {
      return (
        artifactTotal(right.artifact_summary) - artifactTotal(left.artifact_summary) ||
        byNewest(right) - byNewest(left)
      );
    }
    return byNewest(right) - byNewest(left);
  });
  return copy;
}

function resourceTitle(resource: IntelResource) {
  const libraryId = stringMetadata(resource, "library_id") || resource.platform_id;
  if (resource.source_type === "meta_ad_library_ui") {
    return libraryId ? `${resource.brand_name} Meta ad ${libraryId}` : `${resource.brand_name} Meta ad`;
  }
  if (resource.source_type === "google_atc") {
    const advertiser = stringMetadata(resource, "advertiser_name") || resource.brand_name;
    const format = stringMetadata(resource, "format");
    return format ? `${advertiser} · ${format} ad` : `${advertiser} ATC ad`;
  }
  return normalizeDisplayText(resource.title || resource.platform_id || resource.id);
}

function resourceCopy(resource: IntelResource) {
  const text = normalizeDisplayText(resource.description || stringMetadata(resource, "raw_card_text"));
  if (resource.source_type !== "meta_ad_library_ui") {
    return text;
  }
  return cleanMetaCopy(resource.brand_name, text);
}

function resourceFacts(resource: IntelResource) {
  const facts: Array<{ label: string; value: string }> = [];

  if (resource.source_type === "google_atc") {
    const advertiser = stringMetadata(resource, "advertiser_name");
    const format = stringMetadata(resource, "format");
    const lastShown = epochMetadataDate(resource, "last_shown");
    if (advertiser) facts.push({ label: "Advertiser", value: advertiser });
    if (format) facts.push({ label: "Format", value: format });
    if (resource.published_at)
      facts.push({ label: "First shown", value: formatDate(resource.published_at) });
    if (lastShown) facts.push({ label: "Last shown", value: lastShown });
    return facts;
  }

  const libraryId = stringMetadata(resource, "library_id") || resource.platform_id;
  const status = stringMetadata(resource, "status");
  const started = stringMetadata(resource, "started_running");
  const platforms = listMetadata(resource, "platforms");
  const variants = metaVariantCount(resource);
  const videos = videoTotal(resource);

  if (libraryId) facts.push({ label: "Library ID", value: libraryId });
  if (status) facts.push({ label: "Status", value: status });
  if (started) facts.push({ label: "Started", value: started });
  if (platforms.length > 0) facts.push({ label: "Platforms", value: platforms.join(", ") });
  if (variants > 0) facts.push({ label: "Versions", value: String(variants) });
  else if (resource.has_variants) facts.push({ label: "Versions", value: "multiple" });
  if (videos > 0) facts.push({ label: "Videos", value: String(videos) });
  return facts;
}

function epochMetadataDate(resource: IntelResource, key: string) {
  const value = resource.metadata[key];
  if (typeof value !== "number" || !Number.isFinite(value)) return "";
  return new Date(value * 1000).toISOString().slice(0, 10);
}

function metaVariantCount(resource: IntelResource) {
  // Prefer the projection column written by the backend; fall back to metadata / raw text.
  if (typeof resource.variant_count === "number" && Number.isFinite(resource.variant_count)) {
    return resource.variant_count;
  }
  const value = resource.metadata.creative_variant_count;
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  const rawText = normalizeDisplayText(
    resource.description || stringMetadata(resource, "raw_card_text")
  );
  const match = rawText.match(/\b([0-9]+)\s+ads?\s+use\s+this\s+creative\s+and\s+text\b/i);
  return match ? Number(match[1]) : 0;
}

function resourceHasVariants(resource: IntelResource) {
  return Boolean(resource.has_variants) || metaVariantCount(resource) > 1;
}

function variantsLabel(resource: IntelResource) {
  const count = metaVariantCount(resource);
  return count > 1 ? `${count} versions` : "multi-version";
}

function videoTotal(resource: IntelResource) {
  const value = resource.metadata.video_count;
  const declared = typeof value === "number" && Number.isFinite(value) ? value : 0;
  return declared + resource.artifact_summary.video_source_count + resource.artifact_summary.video_poster_count;
}

function stringMetadata(resource: IntelResource, key: string) {
  const value = resource.metadata[key];
  return typeof value === "string" ? normalizeDisplayText(value) : "";
}

function listMetadata(resource: IntelResource, key: string) {
  const value = resource.metadata[key];
  return Array.isArray(value)
    ? value.map((item) => normalizeDisplayText(String(item))).filter(Boolean)
    : [];
}

function cleanMetaCopy(brandName: string, value: string) {
  let text = value;
  const marker = `${brandName} Sponsored`;
  if (text.includes(marker)) {
    text = text.split(marker, 2)[1] ?? "";
  } else {
    const brandMarker = new RegExp(
      `\\b${escapeRegExp(brandName)}(?:\\s+USA)?\\s+Sponsored\\b`,
      "i"
    );
    const match = brandMarker.exec(text);
    if (match?.index !== undefined) {
      text = text.slice(match.index + match[0].length);
    }
  }
  text = text.replace(/\b(?:Active|Inactive)?\s*Library\s+ID[:\s]*[0-9]+\b/gi, " ");
  text = text.replace(
    /^\s*(?:Active|Inactive)?\s*(?:Low|Medium|High)?\s*impression\s+count\s+(?:Impressions:\s*<?[0-9,]+)?\s*(?:See ad)?\s*/i,
    " "
  );
  text = text.replace(/\b(?:Low|Medium|High)\s+impression\s+count\b/gi, " ");
  text = text.replace(
    /\bStarted\s+running\s+on\s+.+?(?=\b(?:Platforms|This ad|Open Dropdown|See summary|Details)\b|$)/gi,
    " "
  );
  text = text.replace(
    /\bThis\s+ad\s+has\s+multiple\s+versions\b.*?\bcreative\s+and\s+text\b/gi,
    " "
  );
  text = text.replace(/\b(?:Platforms|Open Dropdown|See summary details?|Details)\b/gi, " ");
  text = text.replace(/\b(?:Facebook|Instagram|Messenger|Audience Network|Threads)\b/g, " ");
  return normalizeDisplayText(text);
}

function normalizeDisplayText(value: string) {
  return value.replace(/\u200B/g, "").replace(/\s+/g, " ").trim();
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function Metric({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="watcher-metric">
      <strong>{typeof value === "number" ? value.toLocaleString() : value}</strong>
      <span>{label}</span>
    </div>
  );
}

function platformForSourceType(nextSourceType: string) {
  if (nextSourceType === "meta_ad_library_ui") return "meta";
  if (nextSourceType === "youtube_channel") return "youtube";
  return null;
}

function formatDate(value: string | null | undefined) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toISOString().slice(0, 10);
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Request failed";
}
