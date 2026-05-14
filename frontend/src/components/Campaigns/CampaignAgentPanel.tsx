import { useState } from "react";

import { SparkleIcon } from "../../lib/icons";
import type { CampaignDeepFinding, CampaignDeepResearch } from "../../lib/types";

export function CampaignAgentPanel({
  deepResearch,
  loading,
  onRunDeepResearch
}: {
  deepResearch?: CampaignDeepResearch;
  loading?: boolean;
  onRunDeepResearch: (question?: string) => void;
}) {
  const [question, setQuestion] = useState("");
  const submittedQuestion = question.trim();

  return (
    <div className="campaign-tab-pane">
      <section className="campaign-section first">
        <div className="campaign-agent-head">
          <div>
            <div className="section-title">Research agent</div>
            <div className="campaign-agent-status">
              <span className="badge badge-emerald">Local evidence</span>
              <span className="badge badge-violet">LLM answer</span>
              <span className="badge badge-mono">Web off</span>
            </div>
          </div>
          <button
            className="btn btn-primary"
            onClick={() => onRunDeepResearch(submittedQuestion || undefined)}
            disabled={loading}
          >
            <SparkleIcon size={11} />
            <span>{loading ? "Researching" : "Research"}</span>
          </button>
        </div>
        <textarea
          className="input campaign-agent-question"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Ask about outliers, offer consistency, fine print, or campaign improvements"
          rows={2}
        />
      </section>

      {!deepResearch ? (
        <div className="campaign-agent-empty">
          <span>Scope</span>
          <p>Local campaign, ad, classification, and marketing-entity evidence.</p>
        </div>
      ) : (
        <div className="campaign-agent-report">
          {deepResearch.question_answer ? (
            <section>
              <div className="section-title">Answer</div>
              <div className="campaign-agent-answer">
                <strong>{deepResearch.question_answer.question}</strong>
                <p>{deepResearch.question_answer.answer}</p>
                <small>
                  {[
                    deepResearch.question_answer.source,
                    deepResearch.question_answer.finish_reason,
                    deepResearch.question_answer.limits
                  ]
                    .filter(Boolean)
                    .join(" / ")}
                </small>
              </div>
            </section>
          ) : null}
          <section>
            <div className="section-title">Findings</div>
            <FindingList findings={deepResearch.findings} />
          </section>
          <section>
            <div className="section-title">Creative review</div>
            <div className="abcd-grid">
              {deepResearch.creative_review.map((item) => (
                <div key={item.area} className="abcd-card">
                  <span>{item.area}</span>
                  <strong>{item.status}</strong>
                  <p>{item.detail}</p>
                </div>
              ))}
            </div>
          </section>
          <section>
            <div className="section-title">Suggested edits</div>
            <SuggestedEdits suggestions={deepResearch.suggested_edits} />
          </section>
          <section>
            <div className="section-title">Assignment review</div>
            <AssignmentReview report={deepResearch} />
          </section>
          <section>
            <div className="section-title">Open questions</div>
            <div className="prompt-list compact">
              {deepResearch.open_questions.map((question) => (
                <span key={question}>{question}</span>
              ))}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

function FindingList({ findings }: { findings: CampaignDeepFinding[] }) {
  if (!findings.length) return <div className="obs-empty">No findings generated.</div>;
  return (
    <div className="finding-list">
      {findings.map((finding) => (
        <div key={`${finding.title}-${finding.detail}`} className="finding-row">
          <span className={`priority ${finding.priority}`}>{finding.priority}</span>
          <div>
            <strong>{finding.title}</strong>
            <p>{finding.detail}</p>
            <small>{finding.evidence_ad_ids.join(", ") || "No ad ids"}</small>
          </div>
        </div>
      ))}
    </div>
  );
}

function SuggestedEdits({ suggestions }: { suggestions: CampaignDeepResearch["suggested_edits"] }) {
  if (!suggestions.length) return <div className="obs-empty">No local edit suggestions.</div>;
  return (
    <div className="suggested-edits">
      {suggestions.map((suggestion) => (
        <div key={`${suggestion.field}-${suggestion.value}`}>
          <span>{suggestion.field}</span>
          <strong>{suggestion.value}</strong>
          <p>{suggestion.reason}</p>
        </div>
      ))}
    </div>
  );
}

function AssignmentReview({ report }: { report: CampaignDeepResearch }) {
  const review = report.assignment_review;
  return (
    <div className="assignment-review">
      <span>{review.outliers.length} outliers</span>
      <span>{review.missing_offer_ads.filter(Boolean).length} missing offers</span>
      <span>{review.missing_cta_ads.filter(Boolean).length} missing CTAs</span>
      <span>{review.missing_product_ads.filter(Boolean).length} missing products</span>
    </div>
  );
}
