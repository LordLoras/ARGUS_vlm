import { getInitialGraph, expandNode } from "./graphData";
import type { GraphResponse, ExpandResponse } from "./types";

const USE_MOCK = true;

export interface GraphServiceAdapter {
  getInitialGraph: () => Promise<GraphResponse>;
  expandNode: (nodeId: string) => Promise<ExpandResponse>;
}

const mockService: GraphServiceAdapter = {
  getInitialGraph,
  expandNode,
};

const apiService: GraphServiceAdapter = {
  getInitialGraph: async () => {
    const res = await fetch("/api/graph");
    return res.json();
  },
  expandNode: async (nodeId: string) => {
    const res = await fetch(`/api/graph/expand?node_id=${encodeURIComponent(nodeId)}`);
    return res.json();
  },
};

export const graphService: GraphServiceAdapter = USE_MOCK ? mockService : apiService;
