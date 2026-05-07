import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "./components/AppShell";
import { Topbar } from "./components/Topbar";
import { EmptyState } from "./components/shared/EmptyState";
import { Agent } from "./pages/Agent";
import { Campaigns } from "./pages/Campaigns";
import { Library } from "./pages/Library";
import { SearchPage } from "./pages/SearchPage";
import { Upload } from "./pages/Upload";

function Placeholder({ title, hint }: { title: string; hint?: string }) {
  return (
    <>
      <Topbar crumbs={["System", title]} />
      <div className="page">
        <div className="page-head">
          <div>
            <h1 className="page-title">{title}</h1>
            <p className="page-sub">Reserved for a later build.</p>
          </div>
        </div>
        <div style={{ padding: 32 }}>
          <EmptyState
            title="Not implemented yet"
            hint={hint ?? "This operational view will arrive in a follow-up phase."}
          />
        </div>
      </div>
    </>
  );
}

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Navigate to="/library" replace />} />
        <Route path="/library" element={<Library />} />
        <Route path="/upload" element={<Upload />} />
        <Route path="/search" element={<SearchPage />} />
        <Route path="/campaigns" element={<Campaigns />} />
        <Route path="/agent" element={<Agent />} />
        <Route path="/pipelines" element={<Placeholder title="Pipelines" />} />
        <Route path="/embeddings" element={<Placeholder title="Embeddings" />} />
        <Route path="/settings" element={<Placeholder title="Settings" />} />
      </Route>
    </Routes>
  );
}
