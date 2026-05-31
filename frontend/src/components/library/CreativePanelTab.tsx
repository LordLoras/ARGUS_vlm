import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api } from "../../lib/api-client";
import { SparkleIcon } from "../../lib/icons";
import type { CreativePanelReport, PanelCitation } from "../../lib/types";
import { TimestampChip } from "../shared/TimestampChip";

export function CreativePanelTab({
  adId,
  onSeek
}: {
  adId: string;
  onSeek?: (timeMs: number) => void;
}) {
  const [selected, setSelected] = useState<string[]>([]);
  const [report, setReport] = useState<CreativePanelReport | null>(null);
  const personasQuery = useQuery({
    queryKey: ["creative-panel-personas"],
    queryFn: api.listCreativePanelPersonas
  });
  const personas = personasQuery.data?.items ?? [];
  const mutation = useMutation({
    mutationFn: () => api.createCreativePanel(adId, selected),
    onSuccess: setReport
  });

  useEffect(() => {
    setReport(null);
    mutation.reset();
  }, [adId]);

  useEffect(() => {
    if (selected.length === 0 && personas.length > 0) {
      setSelected(personas.slice(0, 4).map((persona) => persona.id));
    }
  }, [personas, selected.length]);

  const togglePersona = (personaId: string) => {
    setSelected((current) => {
      if (current.includes(personaId)) return current.filter((id) => id !== personaId);
      if (current.length >= 6) return current;
      return [...current, personaId];
    });
  };

  return (
    <div className="dcard">
      <div className="dcard-head">
        <span>Synthetic Creative Analysis Panel</span>
        {report ? <span className="count-pill">{report.personas.length}</span> : null}
      </div>
      <div className="dcard-body">
        <div className="panel-caveat">
          Simulated creative analysis grounded in stored ARGUS evidence. Not a focus group,
          demographic sample, or market forecast.
        </div>

        <div className="panel-personas">
          {personas.map((persona) => {
            const active = selected.includes(persona.id);
            return (
              <button
                key={persona.id}
                type="button"
                className={`panel-persona ${active ? "active" : ""}`}
                onClick={() => togglePersona(persona.id)}
                title={persona.lens}
              >
                <span className={`check ${active ? "on" : ""}`} />
                <strong>{persona.label}</strong>
                <small>{persona.lens}</small>
              </button>
            );
          })}
        </div>

        <div className="panel-toolbar">
          <button
            className="btn btn-primary"
            disabled={mutation.isPending || selected.length === 0}
            onClick={() => mutation.mutate()}
          >
            <SparkleIcon size={12} />
            <span>{mutation.isPending ? "Analyzing" : report ? "Run again" : "Run panel"}</span>
          </button>
          <span className="mono panel-meta">
            {report
              ? `${report.analysis_source}${report.source_model ? ` / ${report.source_model}` : ""}`
              : `${selected.length} personas selected`}
          </span>
        </div>

        {mutation.isError ? <div className="obs-empty">Creative panel failed.</div> : null}
        {report?.fallback_error ? (
          <div className="obs-empty">VLM fallback: {report.fallback_error}</div>
        ) : null}

        {report ? (
          <div className="panel-report">
            <section className="panel-summary">
              <SummaryList title="Consensus" items={report.moderator_summary.consensus} />
              <SummaryList title="Clarity Issues" items={report.moderator_summary.message_clarity_issues} />
              <SummaryList title="Strongest Hooks" items={report.moderator_summary.strongest_hooks} />
              <SummaryList title="A/B Variants" items={report.moderator_summary.suggested_ab_variants} />
            </section>

            <div className="panel-reactions">
              {report.personas.map((reaction) => (
                <div className="panel-reaction" key={reaction.persona_id}>
                  <div className="panel-reaction-head">
                    <strong>{reaction.persona_label}</strong>
                    <span>{reaction.emotional_reaction}</span>
                  </div>
                  <p>{reaction.first_impression}</p>
                  <p>{reaction.understood_product_or_offer}</p>
                  <ReactionField label="Likely objection" value={reaction.likely_objection} />
                  <ReactionField label="CTA read" value={reaction.cta_likelihood} />
                  <ReactionList label="Trust" items={reaction.trust_points} />
                  <ReactionList label="Confusion" items={reaction.confusion_points} />
                  <CitationList citations={reaction.citations} onSeek={onSeek} />
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function SummaryList({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <span>{title}</span>
      {items.length ? (
        items.map((item, index) => <p key={`${title}-${index}`}>{item}</p>)
      ) : (
        <p className="muted">No items.</p>
      )}
    </div>
  );
}

function ReactionField({ label, value }: { label: string; value: string }) {
  return (
    <div className="panel-field">
      <span>{label}</span>
      <p>{value}</p>
    </div>
  );
}

function ReactionList({ label, items }: { label: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <div className="panel-field">
      <span>{label}</span>
      <ul>
        {items.map((item, index) => (
          <li key={`${label}-${index}`}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function CitationList({
  citations,
  onSeek
}: {
  citations: PanelCitation[];
  onSeek?: (timeMs: number) => void;
}) {
  if (!citations.length) return null;
  return (
    <div className="panel-citations">
      {citations.map((citation, index) => (
        <div key={`${citation.source}-${index}`}>
          <TimestampChip timeMs={citation.time_ms} onSeek={onSeek} />
          <span className="badge badge-mono">{citation.source}</span>
          <p>{citation.text}</p>
        </div>
      ))}
    </div>
  );
}
