export type NodeType = "brand" | "company" | "category" | "product" | "subsidiary" | "future" | "research";

export interface GraphNode {
  id: string;
  label: string;
  type: NodeType;
  description?: string;
  industries?: string[];
  founded?: string;
  headquarters?: string;
  website?: string;
  parentCompany?: string;
  subsidiaries?: string[];
  products?: string[];
  categories?: string[];
  // Visual properties set client-side
  color?: string;
  val?: number;
  x?: number;
  y?: number;
  z?: number;
  fx?: number;
  fy?: number;
  fz?: number;
  __bckgDimensions?: [number, number];
}

export interface GraphLink {
  source: string | GraphNode;
  target: string | GraphNode;
  label?: string;
  strength?: number;
}

export interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

export interface GraphMeta {
  total_nodes: number;
  total_links: number;
  seed_node: string;
}

export interface GraphResponse {
  nodes: GraphNode[];
  links: GraphLink[];
  meta: GraphMeta;
}

export interface ExpandResponse {
  new_nodes: GraphNode[];
  new_links: GraphLink[];
  expanded_from: string;
}

export const NODE_TYPE_COLORS: Record<NodeType, string> = {
  brand: "#6366f1",
  company: "#38bdf8",
  category: "#34d399",
  product: "#fbbf24",
  subsidiary: "#fb7185",
  future: "#22d3ee",
  research: "#f97316",
};

export const NODE_TYPE_SIZES: Record<NodeType, number> = {
  company: 8,
  brand: 6,
  subsidiary: 5,
  category: 5,
  product: 4,
  future: 5.5,
  research: 4.8,
};

export const NODE_TYPE_LABELS: Record<NodeType, string> = {
  brand: "Brand",
  company: "Company",
  category: "Category",
  product: "Product",
  subsidiary: "Subsidiary",
  future: "Future Signal",
  research: "Research Brief",
};
