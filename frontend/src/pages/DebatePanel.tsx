import { useMutation, useQuery } from "@tanstack/react-query";
import {
  BrainCircuit,
  Gavel,
  MessageSquareQuote,
  Play,
  RefreshCcw,
  Scale,
  Search,
  ShieldCheck,
  Sparkles,
  Swords,
  Target
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { ApiOfflineBanner } from "../components/shared/ApiOfflineBanner";
import { CategoryBadge } from "../components/shared/CategoryBadge";
import { EmptyState } from "../components/shared/EmptyState";
import { FrameThumbnail } from "../components/shared/FrameThumbnail";
import { TimestampChip } from "../components/shared/TimestampChip";
import { Topbar } from "../components/Topbar";
import { useApiHealth } from "../hooks/useApiHealth";
import { api } from "../lib/api-client";
import { formatDuration } from "../lib/format";
import type {
  AdRecord,
  CreativeDebateReport,
  CreativePanelPersona,
  DebateTurn,
  PanelCitation,
  PersonaReaction
} from "../lib/types";

const DEFAULT_TOPIC = "Should the creative lead with the hook, proof, or next step?";

export function DebatePanel() {
  const navigate = useNavigate();
  const health = useApiHealth();
  const [query, setQuery] = useState("");
  const [brand, setBrand] = useState("");
  const [selectedAdId, setSelectedAdId] = useState<string | null>(null);
  const [selectedPersonaIds, setSelectedPersonaIds] = useState<string[]>([]);
  const [topic, setTopic] = useState(DEFAULT_TOPIC);
  const [useVlm, setUseVlm] = useState(true);
  const [enableReasoning, setEnableReasoning] = useState(true);
  const [report, setReport] = useState<CreativeDebateReport | null>(null);

  const adsQuery = useQuery({
    queryKey: ["debate-ads", query, brand],
    queryFn: () =>
      api.listAds({
        q: query || undefined,
        brand: brand || undefined,
        status: "completed",
        limit: 100
      }),
    retry: false
  });

  const personasQuery = useQuery({
    queryKey: ["creative-panel-personas"],
    queryFn: api.listCreativePanelPersonas,
    retry: false
  });

  const ads = adsQuery.data?.items ?? [];
  const personas = personasQuery.data?.items ?? [];
  const selectedAd = ads.find((ad) => ad.id === selectedAdId) ?? ads[0] ?? null;

  const framesQuery = useQuery({
    queryKey: ["debate-frames", selectedAdId],
    queryFn: () => api.getFrames(selectedAdId ?? ""),
    enabled: Boolean(selectedAdId),
    retry: false
  });
  const selectedFrame =
    framesQuery.data?.items.find((frame) => Boolean(frame.kept)) ?? framesQuery.data?.items[0];

  useEffect(() => {
    if (!selectedAdId && ads[0]) setSelectedAdId(ads[0].id);
  }, [ads, selectedAdId]);

  useEffect(() => {
    if (selectedPersonaIds.length === 0 && personas.length > 0) {
      setSelectedPersonaIds(personas.slice(0, 4).map((persona) => persona.id));
    }
  }, [personas, selectedPersonaIds.length]);

  useEffect(() => {
    setReport(null);
  }, [selectedAdId]);

  const selectedPersonas = useMemo(
    () => personas.filter((persona) => selectedPersonaIds.includes(persona.id)),
    [personas, selectedPersonaIds]
  );

  const mutation = useMutation({
    mutationFn: () => {
      if (!selectedAdId) throw new Error("Select an ad first");
      return api.createCreativeDebate(selectedAdId, {
        personaIds: selectedPersonaIds,
        topic: topic.trim() || DEFAULT_TOPIC,
        useVlm,
        enableReasoning
      });
    },
    onSuccess: setReport
  });

  const togglePersona = (personaId: string) => {
    setSelectedPersonaIds((current) => {
      if (current.includes(personaId)) return current.filter((id) => id !== personaId);
      if (current.length >= 6) return current;
      return [...current, personaId];
    });
  };

  const runDebate = () => {
    if (!selectedAdId || selectedPersonaIds.length === 0 || mutation.isPending) return;
    mutation.mutate();
  };

  const phases = report
    ? [
        { key: "opening", label: "Opening", items: report.opening_statements },
        { key: "cross", label: "Cross-exam", items: report.cross_examination },
        { key: "closing", label: "Closing", items: report.closing_statements }
      ]
    : [];

  const allTurns = report
    ? [
        ...report.opening_statements,
        ...report.cross_examination,
        ...report.closing_statements
      ]
    : [];
  const citations = uniqueCitations(allTurns.flatMap((turn) => turn.citations));
  const participantRows: Array<PersonaReaction | CreativePanelPersona> =
    report?.participants ?? selectedPersonas;

  return (
    <>
      <Topbar
        crumbs={["Intelligence", "Debate Panel", selectedAd?.brand_name || "Ad"]}
        actions={
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            disabled={!selectedAd}
            onClick={() => selectedAd && navigate(`/library?ad=${encodeURIComponent(selectedAd.id)}&tab=panel`)}
          >
            <Target size={12} />
            <span>Open ad</span>
          </button>
        }
      />
      <ApiOfflineBanner offline={health.isError || adsQuery.isError || personasQuery.isError} />

      <div className="debate-layout">
        <aside className="debate-rail debate-rail-left">
          <div className="debate-rail-head">
            <div>
              <span className="eyebrow">Debate docket</span>
              <strong>{ads.length} completed ads</strong>
            </div>
            <Swords size={18} />
          </div>

          <div className="debate-search">
            <label className="search-field">
              <span className="search-label">Search</span>
              <div className="debate-input-icon">
                <Search size={13} />
                <input
                  className="input"
                  name="debate_search"
                  autoComplete="off"
                  placeholder="Brand, offer, product…"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                />
              </div>
            </label>
            <label className="search-field">
              <span className="search-label">Brand</span>
              <input
                className="input"
                name="debate_brand"
                autoComplete="off"
                placeholder="Any brand"
                value={brand}
                onChange={(event) => setBrand(event.target.value)}
              />
            </label>
          </div>

          <div className="debate-ad-list">
            {adsQuery.isLoading ? (
              <div className="obs-empty">Loading ads…</div>
            ) : ads.length === 0 ? (
              <div className="obs-empty">No completed ads.</div>
            ) : (
              ads.map((ad) => (
                <AdChoice
                  key={ad.id}
                  ad={ad}
                  active={ad.id === selectedAdId}
                  onClick={() => setSelectedAdId(ad.id)}
                />
              ))
            )}
          </div>
        </aside>

        <main className="debate-main">
          <section className="debate-command">
            <div className="debate-selected">
              <FrameThumbnail
                path={selectedFrame?.path ?? null}
                ar={selectedAd?.width && selectedAd.height ? `${selectedAd.width}:${selectedAd.height}` : undefined}
                seedA="#164e63"
                seedB="#4c1d95"
                className="debate-selected-thumb"
              />
              <div>
                <span className="eyebrow">Selected ad</span>
                <h1>{selectedAd?.brand_name || selectedAd?.advertiser_name || selectedAd?.id || "No ad selected"}</h1>
                <div className="debate-selected-meta">
                  <span>{selectedAd?.id ?? "ad_…"}</span>
                  <span>{formatDuration(selectedAd?.duration_ms)}</span>
                  {selectedAd?.primary_category ? <CategoryBadge category={selectedAd.primary_category} /> : null}
                </div>
              </div>
            </div>

            <div className="debate-topic-wrap">
              <label className="search-field">
                <span className="search-label">Debate topic</span>
                <input
                  className="input debate-topic"
                  name="debate_topic"
                  autoComplete="off"
                  value={topic}
                  onChange={(event) => setTopic(event.target.value)}
                />
              </label>
              <button
                type="button"
                className="btn btn-primary debate-run"
                disabled={!selectedAdId || selectedPersonaIds.length === 0 || mutation.isPending}
                onClick={runDebate}
              >
                {mutation.isPending ? <RefreshCcw size={13} className="spin-icon" /> : <Play size={13} />}
                <span>{mutation.isPending ? "Debating" : report ? "Run again" : "Run debate"}</span>
              </button>
            </div>
          </section>

          <section className="debate-persona-strip" aria-label="Debate personas">
            {personas.map((persona) => (
              <PersonaToggle
                key={persona.id}
                persona={persona}
                active={selectedPersonaIds.includes(persona.id)}
                onClick={() => togglePersona(persona.id)}
              />
            ))}
          </section>

          {mutation.isError ? (
            <div className="panel-caveat">Debate failed: {errorText(mutation.error)}</div>
          ) : null}

          {mutation.isPending ? (
            <DebateLoading personas={selectedPersonas} />
          ) : report ? (
            <div className="debate-report">
              {report.fallback_error ? (
                <div className="panel-caveat">VLM fallback: {report.fallback_error}</div>
              ) : null}

              <section className="debate-verdict">
                <div className="debate-verdict-main">
                  <span className="eyebrow">Moderator verdict</span>
                  <p>{report.scorecard.moderator_verdict}</p>
                </div>
                <div className="debate-verdict-grid">
                  <Metric label="Source" value={report.analysis_source} icon={<BrainCircuit size={14} />} />
                  <Metric label="Turns" value={String(allTurns.length)} icon={<MessageSquareQuote size={14} />} />
                  <Metric label="Citations" value={String(citations.length)} icon={<ShieldCheck size={14} />} />
                  <Metric label="Personas" value={String(report.participants.length)} icon={<Scale size={14} />} />
                </div>
              </section>

              <section className="debate-scoregrid">
                <ScoreCard
                  tone="win"
                  title="Strongest argument"
                  value={report.scorecard.strongest_argument}
                />
                <ScoreCard
                  tone="risk"
                  title="Weakest argument"
                  value={report.scorecard.weakest_argument}
                />
                <ListCard title="Unresolved" items={report.scorecard.unresolved_questions} />
                <ListCard title="Next tests" items={report.scorecard.recommended_tests} />
              </section>

              <section className="debate-timeline">
                {phases.map((phase) => (
                  <div className="debate-phase" key={phase.key}>
                    <div className="debate-phase-head">
                      <span>{phase.label}</span>
                      <small>{phase.items.length} turns</small>
                    </div>
                    <div className="debate-turns">
                      {phase.items.map((turn, index) => (
                        <DebateTurnCard key={`${phase.key}-${index}`} turn={turn} />
                      ))}
                    </div>
                  </div>
                ))}
              </section>
            </div>
          ) : (
            <div className="debate-empty">
              <EmptyState
                icon={<Swords size={20} />}
                title="No debate run yet"
                hint="Select the personas, choose the argument, then run a grounded synthetic debate."
              />
            </div>
          )}
        </main>

        <aside className="debate-rail debate-rail-right">
          <div className="context-section">
            <h4>Settings</h4>
            <ToggleRow
              label="Use VLM"
              value={useVlm}
              onChange={setUseVlm}
              icon={<Sparkles size={13} />}
            />
            <ToggleRow
              label="Reasoning"
              value={enableReasoning}
              onChange={setEnableReasoning}
              icon={<BrainCircuit size={13} />}
            />
          </div>

          <div className="context-section">
            <h4>Participants</h4>
            <div className="debate-participants">
              {participantRows.map((persona) => (
                <ParticipantCard key={participantKey(persona)} item={persona} />
              ))}
            </div>
          </div>

          {report ? (
            <>
              <div className="context-section">
                <h4>Tension map</h4>
                <div className="debate-tensions">
                  {report.tensions.map((tension, index) => (
                    <div className="debate-tension" key={`${tension.axis}-${index}`}>
                      <strong>{tension.axis}</strong>
                      <p>{tension.advocate}</p>
                      <p>{tension.skeptic}</p>
                      <span>{tension.moderator_take}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="context-section">
                <h4>Evidence</h4>
                <div className="debate-evidence">
                  {citations.length ? (
                    citations.slice(0, 8).map((citation, index) => (
                      <EvidenceMini key={`${citation.source}-${index}`} citation={citation} />
                    ))
                  ) : (
                    <span className="muted">No citations attached.</span>
                  )}
                </div>
              </div>

              <div className="context-section">
                <h4>Source</h4>
                <div className="tool-list">
                  <div className="tool-row">
                    <span className="name">model</span>
                    <span className="calls">{report.source_model ?? "local"}</span>
                  </div>
                  <div className="tool-row">
                    <span className="name">evidence</span>
                    <span className="calls">{report.evidence_sources.length}</span>
                  </div>
                  <div className="tool-row">
                    <span className="name">json</span>
                    <span className="calls">written</span>
                  </div>
                </div>
              </div>
            </>
          ) : null}
        </aside>
      </div>
    </>
  );
}

function AdChoice({ ad, active, onClick }: { ad: AdRecord; active: boolean; onClick: () => void }) {
  return (
    <button className={`debate-ad ${active ? "active" : ""}`} onClick={onClick} type="button">
      <FrameThumbnail
        path={null}
        ar={ad.width && ad.height ? `${ad.width}:${ad.height}` : undefined}
        seedA="#1f2937"
        seedB="#312e81"
        className="debate-ad-thumb"
      />
      <span>
        <strong>{ad.brand_name || ad.advertiser_name || ad.id}</strong>
        <small>{ad.products_text || ad.primary_category || "No product text"}</small>
        <em>{ad.id}</em>
      </span>
    </button>
  );
}

function PersonaToggle({
  persona,
  active,
  onClick
}: {
  persona: CreativePanelPersona;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button className={`debate-persona ${active ? "active" : ""}`} onClick={onClick} type="button">
      <span className="debate-persona-orb">{initials(persona.label)}</span>
      <strong>{persona.label}</strong>
      <small>{persona.lens}</small>
    </button>
  );
}

function DebateTurnCard({ turn }: { turn: DebateTurn }) {
  return (
    <article className={`debate-turn stance-${turn.stance}`}>
      <div className="debate-turn-head">
        <span className="debate-avatar">{initials(turn.speaker_label)}</span>
        <div>
          <strong>{turn.speaker_label}</strong>
          <small>
            {turn.stance}
            {turn.target_persona_id ? ` -> ${turn.target_persona_id}` : ""}
          </small>
        </div>
        <span className="badge badge-mono">{turn.phase}</span>
      </div>
      <p className="debate-claim">{turn.claim}</p>
      <div className="debate-turn-grid">
        <div>
          <span>Evidence read</span>
          <p>{turn.evidence_read}</p>
        </div>
        <div>
          <span>Pressure test</span>
          <p>{turn.pressure_test}</p>
        </div>
      </div>
      {turn.citations.length ? (
        <div className="debate-turn-citations">
          {turn.citations.slice(0, 2).map((citation, index) => (
            <EvidenceMini key={`${citation.source}-${index}`} citation={citation} />
          ))}
        </div>
      ) : null}
    </article>
  );
}

function DebateLoading({ personas }: { personas: CreativePanelPersona[] }) {
  return (
    <div className="debate-loading">
      <div className="debate-orbit">
        <Gavel size={24} />
      </div>
      <div className="debate-loading-stack">
        {personas.slice(0, 4).map((persona, index) => (
          <div className="debate-loading-row" key={persona.id} style={{ animationDelay: `${index * 120}ms` }}>
            <span>{initials(persona.label)}</span>
            <strong>{persona.label}</strong>
            <em>building argument</em>
          </div>
        ))}
      </div>
    </div>
  );
}

function Metric({ label, value, icon }: { label: string; value: string; icon: JSX.Element }) {
  return (
    <div className="debate-metric">
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ScoreCard({ title, value, tone }: { title: string; value: string; tone: "win" | "risk" }) {
  return (
    <div className={`debate-scorecard ${tone}`}>
      <span>{title}</span>
      <p>{value}</p>
    </div>
  );
}

function ListCard({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="debate-scorecard">
      <span>{title}</span>
      {items.length ? (
        <ul>
          {items.map((item, index) => (
            <li key={`${title}-${index}`}>{item}</li>
          ))}
        </ul>
      ) : (
        <p>No items.</p>
      )}
    </div>
  );
}

function ToggleRow({
  label,
  value,
  onChange,
  icon
}: {
  label: string;
  value: boolean;
  onChange: (value: boolean) => void;
  icon: JSX.Element;
}) {
  return (
    <label className="debate-toggle">
      <span>
        {icon}
        {label}
      </span>
      <input type="checkbox" checked={value} onChange={(event) => onChange(event.target.checked)} />
    </label>
  );
}

function ParticipantCard({ item }: { item: PersonaReaction | CreativePanelPersona }) {
  const label = "persona_label" in item ? item.persona_label : item.label;
  const lens = item.lens;
  const objection = "likely_objection" in item ? item.likely_objection : "Awaiting debate.";
  return (
    <div className="debate-participant">
      <span>{initials(label)}</span>
      <div>
        <strong>{label}</strong>
        <small>{lens}</small>
        <p>{objection}</p>
      </div>
    </div>
  );
}

function EvidenceMini({ citation }: { citation: PanelCitation }) {
  return (
    <div className="debate-citation">
      <div>
        <TimestampChip timeMs={citation.time_ms} />
        <span className="badge badge-mono">{citation.source}</span>
      </div>
      <p>{citation.text}</p>
    </div>
  );
}

function uniqueCitations(citations: PanelCitation[]) {
  const seen = new Set<string>();
  return citations.filter((citation) => {
    const key = `${citation.source}:${citation.time_ms}:${citation.frame_index}:${citation.text}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function participantKey(item: PersonaReaction | CreativePanelPersona) {
  return "persona_id" in item ? item.persona_id : item.id;
}

function initials(label: string) {
  return label
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");
}

function errorText(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}
