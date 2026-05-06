import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useState } from "react";

import { EmptyState } from "../components/shared/EmptyState";
import { Button } from "../components/ui/Button";
import { Card, CardTitle } from "../components/ui/Card";
import { Input, Select } from "../components/ui/Form";
import { api } from "../lib/api-client";

export function SearchPage() {
  const [q, setQ] = useState("");
  const [mode, setMode] = useState("hybrid");
  const [submitted, setSubmitted] = useState("");

  const query = useQuery({
    queryKey: ["search", submitted, mode],
    queryFn: () => api.search({ q: submitted, mode, k: 10 }),
    enabled: submitted.length > 0
  });

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-semibold">Search</h1>
        <p className="mt-1 text-sm text-muted-foreground">Keyword, vector text, and hybrid retrieval over persisted ads.</p>
      </div>
      <Card>
        <div className="flex gap-3">
          <Input value={q} onChange={(event) => setQ(event.target.value)} placeholder="financing, health claim, brand..." className="flex-1" />
          <Select value={mode} onChange={(event) => setMode(event.target.value)} className="w-40">
            <option value="hybrid">hybrid</option>
            <option value="keyword">keyword</option>
            <option value="text">text vector</option>
          </Select>
          <Button variant="primary" onClick={() => setSubmitted(q)}>
            Search
          </Button>
        </div>
      </Card>

      <div className="mt-6">
        {!submitted ? (
          <EmptyState icon={<Search className="h-10 w-10" />} title="Search the local index" body="Run a query after ads have been embedded into sqlite-vec and FTS5." />
        ) : (
          <Card>
            <CardTitle>Results</CardTitle>
            <div className="mt-3 space-y-2">
              {(query.data?.items ?? []).map((hit) => (
                <div key={hit.ad_id} className="flex items-center justify-between rounded-md bg-muted p-3">
                  <span className="font-mono">{hit.ad_id}</span>
                  <span className="font-mono text-xs text-muted-foreground">{hit.score ?? hit.distance ?? "-"}</span>
                </div>
              ))}
              {query.isSuccess && query.data.items.length === 0 && <p className="text-sm text-muted-foreground">No results.</p>}
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}
