import { CloseIcon, ChevronRightIcon } from "../../lib/icons";
import type { GraphNode, GraphData, NodeType } from "./types";
import { NODE_TYPE_COLORS, NODE_TYPE_LABELS } from "./types";

interface Props {
  node: GraphNode;
  graphData: GraphData;
  expanded: boolean;
  onClose: () => void;
  onNavigate: (node: GraphNode) => void;
}

export function NodeDetail({ node, graphData, expanded, onClose, onNavigate }: Props) {
  const connections = getConnections(node.id, graphData);
  const color = NODE_TYPE_COLORS[node.type];
  const typeLabel = NODE_TYPE_LABELS[node.type];

  const incomingCount = connections.incoming.length;
  const outgoingCount = connections.outgoing.length;
  const totalConnections = incomingCount + outgoingCount;

  return (
    <div className="kg-detail">
      <div className="kg-detail-head">
        <div className="kg-detail-title-row">
          <span className="kg-detail-dot" style={{ background: color, boxShadow: `0 0 10px ${color}50` }} />
          <h2 className="kg-detail-title">{node.label}</h2>
        </div>
        <button className="kg-detail-close" onClick={onClose}>
          <CloseIcon size={12} />
        </button>
      </div>

      <div className="kg-detail-body">
        <span className="kg-type-badge" style={{ color, borderColor: `${color}40`, background: `${color}15` }}>
          {typeLabel}
        </span>

        {node.description && <p className="kg-detail-desc">{node.description}</p>}

        <div className="kg-detail-meta">
          {node.industries && node.industries.length > 0 && (
            <div className="kg-meta-row">
              <span className="kg-meta-label">Industry</span>
              <span className="kg-meta-value">{node.industries.join(", ")}</span>
            </div>
          )}
          {node.headquarters && (
            <div className="kg-meta-row">
              <span className="kg-meta-label">HQ</span>
              <span className="kg-meta-value">{node.headquarters}</span>
            </div>
          )}
          {node.founded && (
            <div className="kg-meta-row">
              <span className="kg-meta-label">Founded</span>
              <span className="kg-meta-value">{node.founded}</span>
            </div>
          )}
          {node.parentCompany && (
            <div className="kg-meta-row">
              <span className="kg-meta-label">Parent</span>
              <span className="kg-meta-value">{node.parentCompany}</span>
            </div>
          )}
          {node.website && (
            <div className="kg-meta-row">
              <span className="kg-meta-label">Web</span>
              <span className="kg-meta-value">{node.website}</span>
            </div>
          )}
          {node.categories && node.categories.length > 0 && (
            <div className="kg-meta-row">
              <span className="kg-meta-label">Categories</span>
              <span className="kg-meta-value">{node.categories.join(", ")}</span>
            </div>
          )}
        </div>

        {expanded && (
          <div className="kg-detail-expanded-badge">
            <span className="kg-expanded-pulse" />
            Connections explored
          </div>
        )}

        <div className="kg-detail-connections">
          <div className="kg-conn-header">
            Connections ({totalConnections})
          </div>

          {outgoingCount > 0 && (
            <div className="kg-conn-group">
              <div className="kg-conn-group-label">Outgoing ({outgoingCount})</div>
              <div className="kg-conn-list">
                {connections.outgoing.map((conn) => {
                  const connColor = NODE_TYPE_COLORS[conn.node.type];
                  return (
                    <button
                      key={`out-${conn.node.id}`}
                      className="kg-conn-item"
                      onClick={() => onNavigate(conn.node)}
                    >
                      <span className="kg-conn-dot" style={{ background: connColor }} />
                      <span className="kg-conn-label">{conn.node.label}</span>
                      {conn.linkLabel && <span className="kg-conn-type">{conn.linkLabel}</span>}
                      <ChevronRightIcon size={9} className="kg-conn-chevron" />
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {incomingCount > 0 && (
            <div className="kg-conn-group">
              <div className="kg-conn-group-label">Incoming ({incomingCount})</div>
              <div className="kg-conn-list">
                {connections.incoming.map((conn) => {
                  const connColor = NODE_TYPE_COLORS[conn.node.type];
                  return (
                    <button
                      key={`in-${conn.node.id}`}
                      className="kg-conn-item"
                      onClick={() => onNavigate(conn.node)}
                    >
                      <span className="kg-conn-dot" style={{ background: connColor }} />
                      <span className="kg-conn-label">{conn.node.label}</span>
                      {conn.linkLabel && <span className="kg-conn-type">{conn.linkLabel}</span>}
                      <ChevronRightIcon size={9} className="kg-conn-chevron" />
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

interface ConnectionResult {
  incoming: { node: GraphNode; linkLabel?: string }[];
  outgoing: { node: GraphNode; linkLabel?: string }[];
}

function getConnections(nodeId: string, graphData: GraphData): ConnectionResult {
  const nodeMap = new Map(graphData.nodes.map((n) => [n.id, n]));
  const incoming: { node: GraphNode; linkLabel?: string }[] = [];
  const outgoing: { node: GraphNode; linkLabel?: string }[] = [];

  for (const link of graphData.links) {
    const src = typeof link.source === "string" ? link.source : (link.source as GraphNode).id;
    const tgt = typeof link.target === "string" ? link.target : (link.target as GraphNode).id;

    if (src === nodeId) {
      const target = nodeMap.get(tgt);
      if (target) outgoing.push({ node: target, linkLabel: link.label });
    } else if (tgt === nodeId) {
      const source = nodeMap.get(src);
      if (source) incoming.push({ node: source, linkLabel: link.label });
    }
  }

  return { incoming, outgoing };
}