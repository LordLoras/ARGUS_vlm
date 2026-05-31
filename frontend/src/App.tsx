import { lazy, Suspense, type ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "./components/AppShell";

const About = lazy(() =>
  import("./pages/About").then((m) => ({ default: m.About }))
);

const Agent = lazy(() =>
  import("./pages/Agent").then((m) => ({ default: m.Agent }))
);

const Campaigns = lazy(() =>
  import("./pages/Campaigns").then((m) => ({ default: m.Campaigns }))
);

const DebatePanel = lazy(() =>
  import("./pages/DebatePanel").then((m) => ({ default: m.DebatePanel }))
);

const Jobs = lazy(() =>
  import("./pages/Jobs").then((m) => ({ default: m.Jobs }))
);

const Library = lazy(() =>
  import("./pages/Library").then((m) => ({ default: m.Library }))
);

const SearchPage = lazy(() =>
  import("./pages/SearchPage").then((m) => ({ default: m.SearchPage }))
);

const Settings = lazy(() =>
  import("./pages/Settings").then((m) => ({ default: m.Settings }))
);

const Taxonomy = lazy(() =>
  import("./pages/Taxonomy").then((m) => ({ default: m.Taxonomy }))
);

const Upload = lazy(() =>
  import("./pages/Upload").then((m) => ({ default: m.Upload }))
);

const KnowledgeGraph = lazy(() =>
  import("./pages/KnowledgeGraph").then((m) => ({ default: m.KnowledgeGraph }))
);

const Embeddings = lazy(() =>
  import("./pages/Embeddings").then((m) => ({ default: m.Embeddings }))
);

function RouteFallback() {
  return (
    <div className="page">
      <div className="obs-empty" style={{ padding: 32 }}>Loading…</div>
    </div>
  );
}

function route(node: ReactNode) {
  return (
    <Suspense fallback={<RouteFallback />}>
      {node}
    </Suspense>
  );
}

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Navigate to="/about" replace />} />
        <Route path="/about" element={route(<About />)} />
        <Route path="/library" element={route(<Library />)} />
        <Route path="/upload" element={route(<Upload />)} />
        <Route path="/search" element={route(<SearchPage />)} />
        <Route path="/campaigns" element={route(<Campaigns />)} />
        <Route path="/agent" element={route(<Agent />)} />
        <Route path="/debate" element={route(<DebatePanel />)} />
        <Route path="/graph" element={route(<KnowledgeGraph />)} />
        <Route path="/taxonomy" element={route(<Taxonomy />)} />
        <Route path="/pipelines" element={route(<Jobs />)} />
        <Route path="/embeddings" element={route(<Embeddings />)} />
        <Route path="/settings" element={route(<Settings />)} />
      </Route>
    </Routes>
  );
}
