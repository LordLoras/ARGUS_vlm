import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

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
  const [open, setOpen] = useState(false);
  const queryClient = useQueryClient();
  const health = useApiHealth();

  const campaigns = useQuery({ queryKey: ["campaigns"], queryFn: api.listCampaigns });

  const discover = useMutation({
    mutationFn: api.discoverCampaigns,
    onSuccess: async (data) => {
      const items = (data.proposals as DiscoverProposal[] | undefined) ??
        (data.campaigns?.map((c) => ({
          id: c.id,
          name: c.name,
          brand: c.brand,
          count: 0,
          mean_similarity: null
        })) as DiscoverProposal[]) ??
        [];
      setProposals(items);
      setOpen(true);
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
            <button className="btn btn-primary" disabled title="Manual create — backend route TBD">
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
        open={open}
        proposals={proposals}
        onClose={() => setOpen(false)}
        onAccept={async (ids) => {
          // Phase X: POST /api/campaigns/discover/accept once available
          console.info("accept selected", ids);
          setOpen(false);
        }}
      />
    </>
  );
}
