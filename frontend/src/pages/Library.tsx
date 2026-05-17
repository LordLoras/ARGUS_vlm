import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { AdDetailDrawer } from "../components/AdDetailDrawer";
import { AdTable } from "../components/AdTable";
import { FilterSidebar, type LibraryFilters } from "../components/FilterSidebar";
import { StatStrip } from "../components/library/StatStrip";
import { ApiOfflineBanner } from "../components/shared/ApiOfflineBanner";
import { EmptyState } from "../components/shared/EmptyState";
import { Topbar } from "../components/Topbar";
import { useApiHealth } from "../hooks/useApiHealth";
import { api } from "../lib/api-client";
import { DownloadIcon, LibraryIcon, PlusIcon } from "../lib/icons";
import type { AdDetail, AdRecord } from "../lib/types";

const emptyFilters: LibraryFilters = {
  q: "",
  category: "",
  brand: "",
  hasRiskTags: false,
  risk: ""
};

export function Library() {
  const [filters, setFilters] = useState(emptyFilters);
  const [searchParams, setSearchParams] = useSearchParams();
  const [selectedAdId, setSelectedAdIdState] = useState<string | null>(() => searchParams.get("ad"));
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const health = useApiHealth();
  const queryAdId = searchParams.get("ad");
  const tabParam = searchParams.get("tab");
  const initialDrawerTab =
    tabParam === "edit"
      ? "Edit"
      : tabParam === "related"
        ? "Related"
        : tabParam === "storyboard"
          ? "Storyboard"
          : tabParam === "evidence"
            ? "Evidence"
            : "Overview";

  useEffect(() => {
    if (queryAdId && queryAdId !== selectedAdId) setSelectedAdIdState(queryAdId);
  }, [queryAdId, selectedAdId]);

  const setSelectedAdId = (
    adId: string | null,
    tab?: "related" | "edit" | "evidence" | "storyboard"
  ) => {
    setSelectedAdIdState(adId);
    const next = new URLSearchParams(searchParams);
    if (adId) next.set("ad", adId);
    if (tab) next.set("tab", tab);
    else next.delete("tab");
    if (!adId) next.delete("ad");
    setSearchParams(next, { replace: true });
  };

  const adsQuery = useQuery({
    queryKey: ["ads", filters.q, filters.category, filters.brand],
    queryFn: () =>
      api.listAds({
        q: filters.q || undefined,
        category: filters.category || undefined,
        brand: filters.brand || undefined,
        limit: 100
      })
  });

  const ads = adsQuery.data?.items ?? [];

  const detailQueries = useQueries({
    queries: ads.map((ad) => ({
      queryKey: ["ad-detail", ad.id],
      queryFn: () => api.getAd(ad.id),
      staleTime: 30_000
    }))
  });

  const detailMap = useMemo(() => {
    const pairs = detailQueries
      .map((q) => q.data)
      .filter((detail): detail is AdDetail => Boolean(detail))
      .map((detail) => [detail.ad.id, detail] as const);
    return Object.fromEntries(pairs);
  }, [detailQueries]);

  const activeRisks = filters.risk ? filters.risk.split(",").filter(Boolean) : [];

  const filteredAds = useMemo(() => {
    return ads.filter((ad) => {
      const detail = detailMap[ad.id];
      const riskLabels = detail?.classification?.risk_labels ?? [];
      if (filters.hasRiskTags && riskLabels.length === 0) return false;
      if (activeRisks.length && !activeRisks.every((r) => riskLabels.includes(r))) return false;
      return true;
    });
  }, [ads, detailMap, filters, activeRisks]);

  const counts = useMemo(() => {
    const byCategory: Record<string, number> = {};
    const byRisk: Record<string, number> = {};
    let hasRisk = 0;
    ads.forEach((ad) => {
      const detail = detailMap[ad.id];
      const category = ad.primary_category ?? detail?.classification?.primary_category ?? "";
      const risks = detail?.classification?.risk_labels ?? [];
      if (category) byCategory[category] = (byCategory[category] ?? 0) + 1;
      risks.forEach((r) => (byRisk[r] = (byRisk[r] ?? 0) + 1));
      if (risks.length > 0) hasRisk += 1;
    });
    return { total: ads.length, sensitive: 0, hasRisk, byCategory, byRisk };
  }, [ads, detailMap]);

  const selectedDetail = selectedAdId ? detailMap[selectedAdId] : undefined;

  const framesQuery = useQuery({
    queryKey: ["frames", selectedAdId],
    queryFn: () => api.getFrames(selectedAdId ?? ""),
    enabled: Boolean(selectedAdId)
  });
  const relatedQuery = useQuery({
    queryKey: ["similar", selectedAdId],
    queryFn: () => api.getSimilar(selectedAdId ?? ""),
    enabled: Boolean(selectedAdId)
  });
  const campaignsQuery = useQuery({
    queryKey: ["campaigns"],
    queryFn: () => api.listCampaigns({ limit: 100 }),
    enabled: Boolean(selectedAdId)
  });

  const patchMutation = useMutation({
    mutationFn: ({ adId, patch }: { adId: string; patch: Record<string, unknown> }) =>
      api.patchAd(adId, patch),
    onSuccess: async (updated) => {
      queryClient.setQueryData<AdDetail>(["ad-detail", updated.id], (current) =>
        current ? { ...current, ad: updated } : current
      );
      queryClient.setQueriesData<{ items: AdRecord[]; limit: number; offset: number }>(
        { queryKey: ["ads"] },
        (current) =>
          current
            ? { ...current, items: current.items.map((ad) => (ad.id === updated.id ? updated : ad)) }
            : current
      );
      await queryClient.invalidateQueries({ queryKey: ["ads"] });
      await queryClient.invalidateQueries({ queryKey: ["ad-detail", updated.id] });
    }
  });

  const deleteMutation = useMutation({
    mutationFn: (adId: string) => api.deleteAd(adId, true),
    onSuccess: async (_result, adId) => {
      setSelectedAdId(null);
      await queryClient.invalidateQueries({ queryKey: ["ads"] });
      await queryClient.removeQueries({ queryKey: ["ad-detail", adId] });
      await queryClient.removeQueries({ queryKey: ["frames", adId] });
      await queryClient.removeQueries({ queryKey: ["similar", adId] });
    }
  });

  const assignCampaignMutation = useMutation({
    mutationFn: ({ campaignId, adId }: { campaignId: string; adId: string }) =>
      api.assignAdsToCampaign(campaignId, [adId]),
    onSuccess: async (_result, variables) => {
      await queryClient.invalidateQueries({ queryKey: ["campaigns"] });
      await queryClient.invalidateQueries({ queryKey: ["ad-detail", variables.adId] });
    }
  });

  const totalAds = counts.total;
  const campaignsCount = useMemo(() => {
    const ids = new Set<string>();
    Object.values(detailMap).forEach((d) => d?.campaigns?.forEach((c) => ids.add(c.id)));
    return ids.size;
  }, [detailMap]);
  const brandsCount = useMemo(() => {
    return new Set(ads.map((ad) => ad.brand_name).filter(Boolean) as string[]).size;
  }, [ads]);

  const stats = [
    {
      label: "Total ads",
      value: String(totalAds),
      delta: totalAds ? `${totalAds} indexed` : "—",
      sparkValues: sparkSeed(totalAds || 1, 12)
    },
    {
      label: "Campaigns",
      value: String(campaignsCount),
      delta: campaignsCount ? `${campaignsCount} active` : "—",
      sparkValues: sparkSeed(Math.max(campaignsCount, 1), 12),
      sparkColor: "var(--accent-2)"
    },
    {
      label: "Brands",
      value: String(brandsCount),
      delta: brandsCount ? `${brandsCount} unique` : "—",
      sparkValues: sparkSeed(Math.max(brandsCount, 1), 12),
      sparkColor: "var(--accent-2)"
    }
  ];

  return (
    <>
      <Topbar
        crumbs={["Workspace", "Library"]}
        actions={
          <>
            <button className="btn" disabled title="CSV export — coming soon">
              <DownloadIcon size={11} />
              <span>Export</span>
            </button>
            <button className="btn btn-primary" onClick={() => navigate("/upload")}>
              <PlusIcon size={11} />
              <span>Upload</span>
            </button>
          </>
        }
      />
      <ApiOfflineBanner offline={health.isError} />

      <div className="page">
        <div className="page-head">
          <div>
            <h1 className="page-title">Ad library</h1>
            <p className="page-sub">
              {totalAds} ads · {campaignsCount} campaigns · {brandsCount} brands
              {adsQuery.dataUpdatedAt
                ? ` · refreshed ${new Date(adsQuery.dataUpdatedAt).toLocaleTimeString()}`
                : null}
            </p>
          </div>
        </div>

        <StatStrip stats={stats} />

        <div className="library-body">
          <FilterSidebar
            filters={filters}
            counts={counts}
            onChange={setFilters}
            onClear={() => setFilters(emptyFilters)}
          />

          {adsQuery.isLoading ? (
            <div style={{ padding: 24, color: "var(--fg-mute)", fontSize: 12 }}>
              Loading ads…
            </div>
          ) : filteredAds.length === 0 ? (
            <div style={{ padding: 32 }}>
              <EmptyState
                icon={<LibraryIcon size={18} />}
                title={ads.length === 0 ? "No ads ingested yet" : "No ads match this view"}
                hint={
                  ads.length === 0
                    ? "Upload your first clip from the Upload page to populate the library."
                    : "Try clearing filters or widening date range."
                }
              />
            </div>
          ) : (
            <AdTable
              ads={filteredAds}
              details={detailMap}
              selectedId={selectedAdId}
              onSelect={setSelectedAdId}
            />
          )}
        </div>
      </div>

      {selectedDetail ? (
        <AdDetailDrawer
          detail={selectedDetail}
          frames={framesQuery.data?.items ?? []}
          related={relatedQuery.data}
          onClose={() => setSelectedAdId(null)}
          onSave={(patch) => patchMutation.mutate({ adId: selectedDetail.ad.id, patch })}
          saving={patchMutation.isPending}
          onSelectRelated={(adId) => setSelectedAdId(adId, "related")}
          campaigns={campaignsQuery.data?.items ?? []}
          assigningCampaign={assignCampaignMutation.isPending}
          onAssignCampaign={(campaignId) =>
            assignCampaignMutation.mutate({ campaignId, adId: selectedDetail.ad.id })
          }
          onDelete={() => {
            if (
              window.confirm(
                "Delete this ad and all generated local files? This removes cascaded database rows, FTS/vector indexes, frames, audio, transcript artifacts, manifest output, and the uploaded copy."
              )
            ) {
              deleteMutation.mutate(selectedDetail.ad.id);
            }
          }}
          initialTab={initialDrawerTab}
        />
      ) : null}
    </>
  );
}

function sparkSeed(scale: number, count: number) {
  const max = Math.max(1, scale);
  return Array.from({ length: count }, (_, i) => {
    const v = Math.sin(i * 0.6) + Math.cos(i * 0.21) + 2.3;
    return Math.round((v / 4.5) * max);
  });
}
