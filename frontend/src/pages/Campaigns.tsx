import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  CreateCampaignDialog,
  type CreateCampaignInput
} from "../components/Campaigns/CreateCampaignDialog";
import { CampaignCard } from "../components/Campaigns/CampaignCard";
import { DiscoverDialog, type DiscoverProposal } from "../components/Campaigns/DiscoverDialog";
import { ApiOfflineBanner } from "../components/shared/ApiOfflineBanner";
import { EmptyState } from "../components/shared/EmptyState";
import { Topbar } from "../components/Topbar";
import { useApiHealth } from "../hooks/useApiHealth";
import { api } from "../lib/api-client";
import { CampaignsIcon, PlusIcon, SparkleIcon } from "../lib/icons";

export function Campaigns() {
  const [proposals, setProposals] = useState<DiscoverProposal[]>([]);
  const [discoverOpen, setDiscoverOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const queryClient = useQueryClient();
  const health = useApiHealth();

  const campaigns = useQuery({
    queryKey: ["campaigns"],
    queryFn: () => api.listCampaigns()
  });

  const discover = useMutation({
    mutationFn: api.discoverCampaigns,
    onSuccess: async (data) => {
      const items = (data.proposals as DiscoverProposal[] | undefined) ??
        ((data.discovered as Array<{ campaign: DiscoverProposal; ad_ids?: string[]; mean_similarity?: number }> | undefined)?.map((d) => ({
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
    onSuccess: async () => {
      setDiscoverOpen(false);
      await queryClient.invalidateQueries({ queryKey: ["campaigns"] });
    }
  });

  const create = useMutation({
    mutationFn: (input: CreateCampaignInput) => api.createCampaign(input),
    onSuccess: async () => {
      setCreateOpen(false);
      await queryClient.invalidateQueries({ queryKey: ["campaigns"] });
    }
  });

  const items = campaigns.data?.items ?? [];

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
              <span>Discover</span>
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
        <div className="page-head">
          <div>
            <h1 className="page-title">Campaigns</h1>
            <p className="page-sub">
              {items.length} campaigns · auto-clusters and curated groups
            </p>
          </div>
        </div>

        {campaigns.isLoading ? (
          <div className="obs-empty" style={{ padding: 32 }}>Loading campaigns…</div>
        ) : items.length === 0 ? (
          <div style={{ padding: 32 }}>
            <EmptyState
              icon={<CampaignsIcon size={18} />}
              title="No campaigns yet"
              hint="Run Discover after a few related ads have visual vectors."
            />
          </div>
        ) : (
          <div className="cam-grid">
            {items.map((campaign) => (
              <CampaignCard key={campaign.id} campaign={campaign} />
            ))}
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
    </>
  );
}
