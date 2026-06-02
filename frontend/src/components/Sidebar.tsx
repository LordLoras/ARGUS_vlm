import { NavLink } from "react-router-dom";

import logoUrl from "../../logo-mark.png";
import { useApiHealth } from "../hooks/useApiHealth";
import { cn } from "../lib/utils";
import {
  BenchmarkIcon,
  CampaignsIcon,
  ChatIcon,
  FlowIcon,
  GraphIcon,
  InfoIcon,
  LayersIcon,
  LibraryIcon,
  SearchIcon,
  SettingsIcon,
  UploadIcon
} from "../lib/icons";

type IconComponent = typeof LibraryIcon;

type NavEntry = {
  to: string;
  label: string;
  icon: IconComponent;
  badge?: string | null;
  accentBadge?: boolean;
  variant?: "archived" | "experimental";
};

const submittedPast: NavEntry[] = [
  { to: "/about", label: "Demo Review", icon: InfoIcon, variant: "archived" },
  { to: "/library", label: "Existing Ad Library", icon: LibraryIcon, variant: "archived" },
  { to: "/search", label: "Existing Search", icon: SearchIcon, variant: "archived" },
  { to: "/agent", label: "Existing Agent", icon: ChatIcon, variant: "archived" },
];

const experimental: NavEntry[] = [
  { to: "/experimental/products", label: "Product Entities", icon: LibraryIcon, variant: "experimental" },
  { to: "/experimental/brand-graph", label: "Brand Graph", icon: GraphIcon, variant: "experimental" },
  { to: "/experimental/entity-resolver", label: "Entity Resolver", icon: FlowIcon, variant: "experimental" },
  { to: "/experimental/taxonomy-mapping", label: "Taxonomy Mapping", icon: LayersIcon, variant: "experimental" },
];

const submittedSupport: NavEntry[] = [
  { to: "/upload", label: "Upload", icon: UploadIcon, variant: "archived" },
  { to: "/campaigns", label: "Campaigns", icon: CampaignsIcon, variant: "archived" },
  { to: "/debate", label: "Debate", icon: FlowIcon, variant: "archived" },
  { to: "/graph", label: "Knowledge Graph", icon: GraphIcon, variant: "archived" },
  { to: "/embeddings", label: "Embeddings", icon: LayersIcon, variant: "archived" },
  { to: "/benchmark", label: "Model Benchmark", icon: BenchmarkIcon, variant: "archived" }
];

const system: NavEntry[] = [
  { to: "/pipelines", label: "Jobs", icon: FlowIcon },
  { to: "/taxonomy", label: "Taxonomy", icon: LayersIcon },
  { to: "/settings", label: "Settings", icon: SettingsIcon }
];

export function Sidebar() {
  const health = useApiHealth();
  const healthy = health.status === "success";
  return (
    <aside className="sidebar">
      <div className="brand">
        <img className="brand-logo" src={logoUrl} alt="" />
        <div className="brand-name">ARGUS</div>
        <div className="brand-meta">v0.4</div>
      </div>
      <nav className="nav">
        <div className="nav-section nav-section-archived">Submitted Past Submission</div>
        {submittedPast.map((entry) => (
          <NavItem key={entry.to} entry={entry} />
        ))}
        <div className="nav-section nav-section-experimental">Experimental</div>
        {experimental.map((entry) => (
          <NavItem key={entry.to} entry={entry} />
        ))}
        <div className="nav-section nav-section-archived">Submitted Support</div>
        {submittedSupport.map((entry) => (
          <NavItem key={entry.to} entry={entry} />
        ))}
        <div className="nav-section">System</div>
        {system.map((entry) => (
          <NavItem key={entry.to} entry={entry} />
        ))}
      </nav>
      <div className="sidebar-footer">
        <span className={cn("health-dot", !healthy && "down")} />
        <span>{healthy ? "API healthy" : "API unreachable"}</span>
        <span className="health-meta">:8000</span>
      </div>
    </aside>
  );
}

function NavItem({ entry }: { entry: NavEntry }) {
  const Icon = entry.icon;
  return (
    <NavLink
      to={entry.to}
      className={({ isActive }) =>
        cn(
          "nav-item",
          entry.variant === "archived" && "nav-item-archived",
          entry.variant === "experimental" && "nav-item-experimental",
          isActive && "active"
        )
      }
    >
      <Icon className="nav-icon" />
      <span>{entry.label}</span>
      {entry.badge ? (
        <span className="badge-count" style={entry.accentBadge ? { color: "var(--accent-2)" } : undefined}>
          {entry.badge}
        </span>
      ) : null}
    </NavLink>
  );
}

function DisabledItem({ label, Icon }: { label: string; Icon: IconComponent }) {
  return (
    <span className="nav-item disabled">
      <Icon className="nav-icon" />
      <span>{label}</span>
    </span>
  );
}
