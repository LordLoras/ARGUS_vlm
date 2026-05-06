import {
  Bot,
  Boxes,
  Database,
  LibraryBig,
  Search,
  Settings,
  UploadCloud,
  Workflow
} from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";

import { ApiOfflineBanner } from "./shared/ApiOfflineBanner";
import { useApiHealth } from "../hooks/useApiHealth";
import { cn } from "../lib/utils";

const navGroups = [
  {
    label: "Workspace",
    items: [
      { to: "/library", label: "Library", icon: LibraryBig },
      { to: "/upload", label: "Upload", icon: UploadCloud },
      { to: "/search", label: "Search", icon: Search },
      { to: "/campaigns", label: "Campaigns", icon: Boxes }
    ]
  },
  {
    label: "Intelligence",
    items: [
      { to: "/agent", label: "Agent", icon: Bot },
      { to: "/pipelines", label: "Pipelines", icon: Workflow },
      { to: "/embeddings", label: "Embeddings", icon: Database },
      { to: "/settings", label: "Settings", icon: Settings }
    ]
  }
];

export function AppShell() {
  const health = useApiHealth();

  return (
    <div className="flex min-h-screen">
      <aside className="fixed inset-y-0 left-0 flex w-64 flex-col border-r border-border bg-background/90 px-4 py-5 backdrop-blur">
        <div className="mb-8">
          <div className="text-lg font-semibold">AdScope Local</div>
          <div className="mt-1 font-mono text-xs text-muted-foreground">Argus v0.4</div>
        </div>

        <nav className="space-y-7">
          {navGroups.map((group) => (
            <div key={group.label}>
              <div className="mb-2 px-2 text-xs font-semibold uppercase text-muted-foreground">
                {group.label}
              </div>
              <div className="space-y-1">
                {group.items.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    className={({ isActive }) =>
                      cn(
                        "flex items-center gap-2 rounded-md px-2.5 py-2 text-sm text-muted-foreground transition hover:bg-muted hover:text-foreground",
                        isActive && "bg-violet-500/10 text-violet-100 ring-1 ring-violet-500/25"
                      )
                    }
                  >
                    <item.icon className="h-4 w-4" />
                    {item.label}
                  </NavLink>
                ))}
              </div>
            </div>
          ))}
        </nav>

        <div className="mt-auto rounded-lg border border-border bg-surface p-3 text-xs text-muted-foreground">
          Local SQLite · LM Studio · no cloud services
        </div>
      </aside>

      <main className="ml-64 min-h-screen flex-1">
        <ApiOfflineBanner offline={health.isError} />
        <header className="border-b border-border px-8 py-4">
          <div className="text-xs uppercase text-muted-foreground">Workspace / Local machine</div>
        </header>
        <div className="px-8 py-7">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
