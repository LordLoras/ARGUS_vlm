import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "./components/AppShell";
import { Agent } from "./pages/Agent";
import { Campaigns } from "./pages/Campaigns";
import { Library } from "./pages/Library";
import { SearchPage } from "./pages/SearchPage";
import { Upload } from "./pages/Upload";

function Placeholder({ title }: { title: string }) {
  return (
    <div>
      <h1 className="text-2xl font-semibold">{title}</h1>
      <p className="mt-2 text-sm text-muted-foreground">This operational view is reserved for a later build.</p>
    </div>
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
