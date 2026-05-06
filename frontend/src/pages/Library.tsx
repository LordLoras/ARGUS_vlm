import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { Database, UploadCloud } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { AdDetailDrawer } from "../components/AdDetailDrawer";
import { AdTable } from "../components/AdTable";
import { FilterSidebar, type LibraryFilters } from "../components/FilterSidebar";
import { EmptyState } from "../components/shared/EmptyState";
import { SensitivePill } from "../components/shared/SensitivePill";
import { Button } from "../components/ui/Button";
import { Card, CardTitle } from "../components/ui/Card";
import { api } from "../lib/api-client";
import { sensitiveCategories } from "../lib/taxonomy";
import type { AdDetail } from "../lib/types";

const emptyFilters: LibraryFilters = {
  q: "",
  category: "",
  brand: "",
  sensitiveOnly: false,
  hasRiskTags: false,
  risk: ""
};

export function Library() {
  const [filters, setFilters] = useState(emptyFilters);
  const [selectedAdId, setSelectedAdId] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const adsQuery = useQuery({
    queryKey: ["ads", filters.q, filters.category, filters.brand],
    queryFn: () =>
      api.listAds({
        q: filters.q || undefined,
        category: filters.category || undefined,
        brand: filters.brand || undefined,
        limit: 50
      })
  });

  const detailQueries = useQueries({
    queries: (adsQuery.data?.items ?? []).map((ad) => ({
      queryKey: ["ad-detail", ad.id],
      queryFn: () => api.getAd(ad.id),
      staleTime: 30_000
    }))
  });

  const detailMap = useMemo(() => {
    const pairs = detailQueries
      .map((query) => query.data)
      .filter((detail): detail is AdDetail => Boolean(detail))
      .map((detail) => [detail.ad.id, detail] as const);
    return Object.fromEntries(pairs);
  }, [detailQueries]);

  const filteredAds = useMemo(() => {
    return (adsQuery.data?.items ?? []).filter((ad) => {
      const detail = detailMap[ad.id];
      const category = detail?.classification?.primary_category ?? ad.primary_category ?? "";
      const riskLabels = detail?.classification?.risk_labels ?? [];
      if (filters.sensitiveOnly && !sensitiveCategories.has(category)) return false;
      if (filters.hasRiskTags && riskLabels.length === 0) return false;
      if (filters.risk && !riskLabels.includes(filters.risk)) return false;
      return true;
    });
  }, [adsQuery.data?.items, detailMap, filters]);

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

  const patchMutation = useMutation({
    mutationFn: (patch: { brand_name?: string | null; products_text?: string | null; primary_category?: string | null }) =>
      api.patchAd(selectedAdId ?? "", patch),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["ads"] });
      await queryClient.invalidateQueries({ queryKey: ["ad-detail", selectedAdId] });
    }
  });

  const deleteMutation = useMutation({
    mutationFn: (adId: string) => api.deleteAd(adId),
    onSuccess: async () => {
      setSelectedAdId(null);
      await queryClient.invalidateQueries({ queryKey: ["ads"] });
    }
  });

  const campaignCount = new Set(
    Object.values(detailMap).flatMap((detail) => detail.campaigns?.map((campaign) => campaign.id) ?? [])
  ).size;
  const sensitiveCount = filteredAds.filter((ad) => {
    const category = detailMap[ad.id]?.classification?.primary_category ?? ad.primary_category;
    return sensitiveCategories.has(category ?? "");
  }).length;

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Ad Library</h1>
          <p className="mt-1 text-sm text-muted-foreground">Manage ingested ads, categories, evidence, campaigns, and observations.</p>
        </div>
        <Link
          to="/upload"
          className="inline-flex h-9 items-center justify-center gap-2 rounded-md bg-accent px-3 text-sm font-medium text-accent-foreground transition hover:bg-violet-500"
        >
          <UploadCloud className="h-4 w-4" />
          Upload
        </Link>
      </div>

      <div className="mb-6 grid grid-cols-3 gap-4">
        <Card>
          <CardTitle>Total ads</CardTitle>
          <div className="mt-3 font-mono text-3xl">{adsQuery.data?.items.length ?? 0}</div>
        </Card>
        <Card>
          <CardTitle>Campaigns</CardTitle>
          <div className="mt-3 font-mono text-3xl">{campaignCount}</div>
          <div className="mt-3 h-8 rounded bg-gradient-to-r from-violet-500/25 to-sky-500/15" />
        </Card>
        <Card>
          <div className="flex items-center justify-between">
            <CardTitle>Sensitive</CardTitle>
            <SensitivePill visible={sensitiveCount > 0} />
          </div>
          <div className="mt-3 font-mono text-3xl">{sensitiveCount}</div>
        </Card>
      </div>

      <div className="flex gap-6">
        <FilterSidebar filters={filters} onChange={setFilters} onClear={() => setFilters(emptyFilters)} />
        <div className="min-w-0 flex-1">
          {adsQuery.isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 5 }).map((_, index) => (
                <div key={index} className="h-16 animate-pulse rounded-lg bg-muted" />
              ))}
            </div>
          ) : filteredAds.length === 0 ? (
            <EmptyState
              icon={<Database className="h-10 w-10" />}
              title="No ads match this view"
              body="Clear filters or upload your first local clip to populate the library."
            />
          ) : (
            <AdTable ads={filteredAds} details={detailMap} onSelect={setSelectedAdId} />
          )}
        </div>
      </div>

      {selectedDetail && (
        <AdDetailDrawer
          detail={selectedDetail}
          frames={framesQuery.data?.items ?? []}
          related={relatedQuery.data}
          onClose={() => setSelectedAdId(null)}
          onSave={(patch) => patchMutation.mutate(patch)}
          onDelete={() => {
            if (window.confirm("Delete this ad record? Cascaded database rows will be removed. Local files are left alone.")) {
              deleteMutation.mutate(selectedDetail.ad.id);
            }
          }}
        />
      )}
    </div>
  );
}
