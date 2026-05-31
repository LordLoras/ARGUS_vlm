import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import {
  CreateCampaignDialog,
  type CreateCampaignInput
} from "../components/Campaigns/CreateCampaignDialog";
import { CampaignCard } from "../components/Campaigns/CampaignCard";
import { CampaignDetailPanel } from "../components/Campaigns/CampaignDetailPanel";
import { DiscoverDialog, type DiscoverProposal } from "../components/Campaigns/DiscoverDialog";
import { ApiOfflineBanner } from "../components/shared/ApiOfflineBanner";
import { EmptyState } from "../components/shared/EmptyState";
import { Topbar } from "../components/Topbar";
import { useApiHealth } from "../hooks/useApiHealth";
import { api } from "../lib/api-client";
import { CampaignsIcon, PlusIcon, SearchIcon, SparkleIcon } from "../lib/icons";
import type { Campaign } from "../lib/types";

const CREATED_BY_OPTIONS = [
  { label: "All", value: "" },
  { label: "User", value: "user" },
  { label: "Auto", value: "auto" }
] as const;

export function Campaigns() {
  const [proposals, setProposals] = useState<DiscoverProposal[]>([]);
  const [discoverOpen, setDiscoverOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [createdBy, setCreatedBy] = useState("");
  const [unassigningAdId, setUnassigningAdId] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const health = useApiHealth();

  const campaigns = useQuery({
    queryKey: ["campaigns", q, createdBy],
    queryFn: () =>
      api.listCampaigns({
        q: q || undefined,
        created_by: createdBy || undefined,
        limit: 100
      })
  });

  const items = campaigns.data?.items ?? [];

  useEffect(() => {
    if (items.length === 0) {
      setSelectedId(null);
      return;
    }
    if (!selectedId || !items.some((campaign) => campaign.id === selectedId)) {
      setSelectedId(items[0].id);
    }
  }, [items, selectedId]);

  const detail = useQuery({
    queryKey: ["campaign-detail", selectedId],
    queryFn: () => api.getCampaign(selectedId ?? ""),
    enabled: Boolean(selectedId)
  });

  const selectedCampaign = detail.data?.campaign ?? items.find((campaign) => campaign.id === selectedId);

  const deepResearch = useMutation({
    mutationFn: ({ campaignId, question }: { campaignId: string; question?: string }) =>
      api.runCampaignDeepResearch(campaignId, {
        include_web: false,
        depth: "deep",
        question,
        thinking: false
      })
  });

  useEffect(() => {
    deepResearch.reset();
  }, [selectedId]);

  const discover = useMutation({
    mutationFn: api.discoverCampaigns,
    onSuccess: async (data) => {
      const discovered = data.discovered as
        | Array<{ campaign: DiscoverProposal; ad_ids?: string[]; mean_similarity?: number }>
        | undefined;
      const items = (data.proposals as DiscoverProposal[] | undefined) ??
        (discovered?.map((d) => ({
          ...d.campaign,
          ad_ids: d.ad_ids,
          mean_similarity: d.mean_similarity
        })) as DiscoverProposal[]) ??
        [];
      setProposals(items);
      setDiscoverOpen(true);
    }
  });

  const accept = useMutation({
    mutationFn: (ids: string[]) =>
      api.acceptCampaignProposals({
        campaign_ids: ids,
        proposals: proposals.filter((proposal) => ids.includes(proposal.id))
      }),
    onSuccess: async (data) => {
      setDiscoverOpen(false);
      await queryClient.invalidateQueries({ queryKey: ["campaigns"] });
      await queryClient.invalidateQueries({ queryKey: ["campaign-detail"] });
      const firstAccepted = data.accepted[0];
      if (firstAccepted) setSelectedId(firstAccepted.id);
    }
  });

  const create = useMutation({
    mutationFn: (input: CreateCampaignInput) => api.createCampaign(input),
    onSuccess: async (campaign) => {
      setCreateOpen(false);
      await queryClient.invalidateQueries({ queryKey: ["campaigns"] });
      setSelectedId(campaign.id);
    }
  });

  const update = useMutation({
    mutationFn: ({ campaignId, input }: { campaignId: string; input: CreateCampaignInput }) =>
      api.updateCampaign(campaignId, input),
    onSuccess: async (campaign) => {
      setEditOpen(false);
      deepResearch.reset();
      await queryClient.invalidateQueries({ queryKey: ["campaigns"] });
      await queryClient.invalidateQueries({ queryKey: ["campaign-detail", campaign.id] });
    }
  });

  const remove = useMutation({
    mutationFn: (campaignId: string) => api.deleteCampaign(campaignId),
    onSuccess: async () => {
      setSelectedId(null);
      deepResearch.reset();
      await queryClient.invalidateQueries({ queryKey: ["campaigns"] });
      await queryClient.invalidateQueries({ queryKey: ["campaign-detail"] });
    }
  });

  const assign = useMutation({
    mutationFn: ({ campaignId, adIds }: { campaignId: string; adIds: string[] }) =>
      api.assignAdsToCampaign(campaignId, adIds),
    onSuccess: async (_result, variables) => {
      deepResearch.reset();
      await queryClient.invalidateQueries({ queryKey: ["campaigns"] });
      await queryClient.invalidateQueries({ queryKey: ["campaign-detail", variables.campaignId] });
    }
  });

  const unassign = useMutation({
    mutationFn: ({ campaignId, adId }: { campaignId: string; adId: string }) =>
      api.unassignAdFromCampaign(campaignId, adId),
    onMutate: (variables) => setUnassigningAdId(variables.adId),
    onSettled: () => setUnassigningAdId(null),
    onSuccess: async (_result, variables) => {
      deepResearch.reset();
      await queryClient.invalidateQueries({ queryKey: ["campaigns"] });
      await queryClient.invalidateQueries({ queryKey: ["campaign-detail", variables.campaignId] });
    }
  });

  const totals = useMemo(() => {
    const adCount = items.reduce((sum, campaign) => sum + (campaign.ad_count ?? 0), 0);
    const autoCount = items.filter((campaign) => campaign.created_by === "auto").length;
    return { adCount, autoCount, userCount: items.length - autoCount };
  }, [items]);

  return (
    <>
      <Topbar
        crumbs={["Workspace", "Campaigns"]}
        actions={
          <>
            <button
              className="btn"
              onClick={() => discover.mutate()}
              disabled={discover.isPending}
            >
              <SparkleIcon size={11} />
              <span>{discover.isPending ? "Scanning" : "Discover"}</span>
            </button>
            <button className="btn btn-primary" onClick={() => setCreateOpen(true)}>
              <PlusIcon size={11} />
              <span>New campaign</span>
            </button>
          </>
        }
      />
      <ApiOfflineBanner offline={health.isError} />

      <div className="page">
        <div className="page-head campaign-page-head">
          <div>
            <h1 className="page-title">Campaigns</h1>
            <p className="page-sub">
              {items.length} campaigns / {totals.adCount} assignments / {totals.userCount} user / {totals.autoCount} auto
            </p>
          </div>
          <div className="campaign-filters">
            <label className="campaign-search">
              <SearchIcon size={12} />
              <input
                value={q}
                onChange={(event) => setQ(event.target.value)}
                placeholder="Search campaigns"
              />
            </label>
            <div className="seg-control">
              {CREATED_BY_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  className={createdBy === option.value ? "active" : ""}
                  onClick={() => setCreatedBy(option.value)}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {campaigns.isLoading ? (
          <div className="obs-empty" style={{ padding: 32 }}>Loading campaigns…</div>
        ) : items.length === 0 ? (
          <div style={{ padding: 32 }}>
            <EmptyState
              icon={<CampaignsIcon size={18} />}
              title="No campaigns yet"
              hint="Run discovery after related ads have visual vectors, or create one manually."
            />
          </div>
        ) : (
          <div className="campaign-workbench">
            <aside className="campaign-rail">
              {items.map((campaign) => (
                <CampaignCard
                  key={campaign.id}
                  campaign={campaign}
                  selected={campaign.id === selectedId}
                  onSelect={() => setSelectedId(campaign.id)}
                />
              ))}
            </aside>
            <CampaignDetailPanel
              detail={detail.data}
              deepResearch={deepResearch.data}
              loading={detail.isLoading}
              researchLoading={deepResearch.isPending}
              onEdit={() => setEditOpen(true)}
              onDelete={() => {
                if (
                  selectedId &&
                  window.confirm("Delete this campaign? Assigned ads stay in the library.")
                ) {
                  remove.mutate(selectedId);
                }
              }}
              onAssign={(adIds) => {
                if (selectedId) assign.mutate({ campaignId: selectedId, adIds });
              }}
              assigning={assign.isPending}
              onUnassign={(adId) => {
                if (selectedId) unassign.mutate({ campaignId: selectedId, adId });
              }}
              onRunDeepResearch={(question) => {
                if (selectedId) {
                  deepResearch.mutate({ campaignId: selectedId, question });
                }
              }}
              unassigningAdId={unassigningAdId}
            />
          </div>
        )}
      </div>

      <DiscoverDialog
        open={discoverOpen}
        proposals={proposals}
        onClose={() => setDiscoverOpen(false)}
        onAccept={(ids) => accept.mutate(ids)}
      />
      <CreateCampaignDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreate={(input) => create.mutate(input)}
        saving={create.isPending}
      />
      <CreateCampaignDialog
        open={editOpen}
        onClose={() => setEditOpen(false)}
        onCreate={(input) => {
          if (selectedCampaign) update.mutate({ campaignId: selectedCampaign.id, input });
        }}
        saving={update.isPending}
        initial={campaignToForm(selectedCampaign)}
        title="Edit campaign"
        submitLabel="Save"
      />
    </>
  );
}

function campaignToForm(campaign?: Campaign): Partial<CreateCampaignInput> | undefined {
  if (!campaign) return undefined;
  return {
    name: campaign.name,
    advertiser: campaign.advertiser ?? "",
    brand: campaign.brand ?? "",
    theme: campaign.theme ?? "",
    start_date: campaign.start_date?.slice(0, 10) ?? "",
    end_date: campaign.end_date?.slice(0, 10) ?? "",
    description: campaign.description ?? ""
  };
}
