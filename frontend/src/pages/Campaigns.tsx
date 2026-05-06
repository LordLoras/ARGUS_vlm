import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Boxes, Plus } from "lucide-react";

import { EmptyState } from "../components/shared/EmptyState";
import { Button } from "../components/ui/Button";
import { Card, CardTitle } from "../components/ui/Card";
import { api } from "../lib/api-client";

export function Campaigns() {
  const queryClient = useQueryClient();
  const campaigns = useQuery({ queryKey: ["campaigns"], queryFn: api.listCampaigns });
  const discover = useMutation({
    mutationFn: api.discoverCampaigns,
    onSuccess: async () => queryClient.invalidateQueries({ queryKey: ["campaigns"] })
  });

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Campaigns</h1>
          <p className="mt-1 text-sm text-muted-foreground">Auto-discovered and manually curated ad groups.</p>
        </div>
        <Button variant="primary" onClick={() => discover.mutate()} disabled={discover.isPending}>
          <Plus className="h-4 w-4" />
          Discover campaigns
        </Button>
      </div>

      {(campaigns.data?.items ?? []).length === 0 ? (
        <EmptyState icon={<Boxes className="h-10 w-10" />} title="No campaigns yet" body="Run discovery after a few related ads have visual vectors, or create campaigns through the API." />
      ) : (
        <div className="grid grid-cols-3 gap-4">
          {campaigns.data?.items.map((campaign) => (
            <Card key={campaign.id}>
              <CardTitle>{campaign.created_by ?? "campaign"}</CardTitle>
              <div className="mt-3 text-lg font-semibold">{campaign.name}</div>
              <div className="mt-2 text-sm text-muted-foreground">{campaign.brand || campaign.advertiser || "Unknown brand"}</div>
              <div className="mt-4 font-mono text-xs text-muted-foreground">{campaign.id}</div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
