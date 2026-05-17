from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from ad_classifier.agent.client import AgentClient
from ad_classifier.creative.panel.models import (
    CreativePanelReport,
    ModeratorSummary,
    PanelCitation,
    PersonaReaction,
)
from ad_classifier.db.repositories import AdRepository
from ad_classifier.db.repositories.classifications import ClassificationRepository
from ad_classifier.db.repositories.marketing import MarketingEntityRepository
from ad_classifier.models.classification import ClassificationRecord
from ad_classifier.models.common import EvidenceItem
from ad_classifier.models.marketing import MarketingEntities

logger = structlog.get_logger(__name__)

DEFAULT_PERSONAS = [
    "budget_parent",
    "skeptical_buyer",
    "luxury_shopper",
    "first_time_car_buyer",
]


@dataclass(frozen=True)
class Persona:
    id: str
    label: str
    lens: str


PERSONAS: dict[str, Persona] = {
    "budget_parent": Persona(
        id="budget_parent",
        label="Budget-conscious parent",
        lens="Looks for clear value, practical benefit, total cost, and family relevance.",
    ),
    "skeptical_buyer": Persona(
        id="skeptical_buyer",
        label="Skeptical claim-checker",
        lens="Looks for proof, plain terms, claim support, and anything that feels overstated.",
    ),
    "luxury_shopper": Persona(
        id="luxury_shopper",
        label="Luxury shopper",
        lens="Looks for polish, exclusivity, brand cues, and premium product signals.",
    ),
    "first_time_car_buyer": Persona(
        id="first_time_car_buyer",
        label="First-time car buyer",
        lens="Looks for model clarity, financing terms, ownership confidence, and next steps.",
    ),
    "gen_z_mobile_viewer": Persona(
        id="gen_z_mobile_viewer",
        label="Gen Z mobile-first viewer",
        lens="Looks for fast comprehension, visual hook, direct CTA, and minimal friction.",
    ),
    "compliance_reviewer": Persona(
        id="compliance_reviewer",
        label="Compliance-minded reviewer",
        lens="Looks for qualifiers, disclaimers, substantiation, and clear offer boundaries.",
    ),
}


def list_personas() -> list[dict[str, str]]:
    return [
        {"id": persona.id, "label": persona.label, "lens": persona.lens}
        for persona in PERSONAS.values()
    ]


def build_creative_panel(
    conn: sqlite3.Connection,
    ad_id: str,
    out_root: Path,
    persona_ids: list[str] | None = None,
    *,
    use_vlm: bool = False,
    llm_client: AgentClient | None = None,
    source_model: str | None = None,
    thinking: bool = False,
) -> CreativePanelReport:
    ad = AdRepository(conn).get(ad_id)
    if ad is None:
        raise ValueError("ad not found")

    selected = persona_ids or DEFAULT_PERSONAS
    unknown = [persona_id for persona_id in selected if persona_id not in PERSONAS]
    if unknown:
        raise ValueError(f"unknown persona ids: {', '.join(unknown)}")

    classification = ClassificationRepository(conn).get(ad_id)
    marketing = MarketingEntityRepository(conn).get(ad_id) or MarketingEntities()
    transcript_text = _transcript_text(conn, ad_id)
    ocr_items = _ocr_items(conn, ad_id)
    context = _PanelContext(
        ad_id=ad_id,
        brand=ad.brand_name or marketing.brand.name,
        category=ad.primary_category
        or (classification.primary_category if classification else None),
        products=_products(ad.products_text, marketing),
        offers=[offer.text for offer in marketing.offers],
        prices=[price.text for price in marketing.prices],
        ctas=[cta.text for cta in marketing.ctas],
        disclaimers=[disclaimer.text for disclaimer in marketing.disclaimers],
        risk_labels=classification.risk_labels if classification else [],
        classification=classification,
        marketing=marketing,
        transcript_text=transcript_text,
        ocr_texts=[item.text for item in ocr_items],
        citations=_collect_citations(ad_id, classification, marketing, ocr_items, transcript_text),
    )

    reactions = [_reaction(PERSONAS[persona_id], context) for persona_id in selected]
    moderator_summary = _moderator_summary(context, reactions)
    analysis_source = "deterministic_fallback"
    fallback_error: str | None = None

    if use_vlm and llm_client is not None:
        try:
            reactions, moderator_summary, used_fallback = _run_vlm_panel(
                llm_client,
                selected,
                context,
                fallback_reactions=reactions,
                fallback_summary=moderator_summary,
                thinking=thinking,
            )
            analysis_source = "vlm_with_fallback" if used_fallback else "vlm"
        except Exception as exc:
            fallback_error = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "creative_panel_vlm_failed",
                ad_id=ad_id,
                error=fallback_error,
            )
    elif use_vlm:
        fallback_error = "VLM client unavailable"

    report = CreativePanelReport(
        ad_id=ad_id,
        generated_at=datetime.now(UTC),
        json_path=str(out_root / ad_id / "creative_panel.json"),
        analysis_source=analysis_source,
        source_model=source_model if analysis_source.startswith("vlm") else None,
        fallback_error=fallback_error,
        caveat=(
            "Simulated creative review generated from stored ARGUS evidence. "
            "It is not a real focus group, demographic sample, or market forecast."
        ),
        personas=reactions,
        moderator_summary=moderator_summary,
        evidence_sources=_evidence_sources(context),
    )

    output_dir = out_root / ad_id
    output_dir.mkdir(parents=True, exist_ok=True)
    Path(report.json_path).write_text(
        json.dumps(report.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    return report


@dataclass(frozen=True)
class _OCRItem:
    time_ms: int
    frame_index: int
    engine: str
    text: str


@dataclass(frozen=True)
class _PanelContext:
    ad_id: str
    brand: str | None
    category: str | None
    products: list[str]
    offers: list[str]
    prices: list[str]
    ctas: list[str]
    disclaimers: list[str]
    risk_labels: list[str]
    classification: ClassificationRecord | None
    marketing: MarketingEntities
    transcript_text: str
    ocr_texts: list[str]
    citations: list[PanelCitation]


def _run_vlm_panel(
    client: AgentClient,
    selected: list[str],
    context: _PanelContext,
    *,
    fallback_reactions: list[PersonaReaction],
    fallback_summary: ModeratorSummary,
    thinking: bool,
) -> tuple[list[PersonaReaction], ModeratorSummary, bool]:
    fallback_by_id = {reaction.persona_id: reaction for reaction in fallback_reactions}
    reactions: list[PersonaReaction] = []
    used_fallback = False
    used_vlm = False

    for persona_id in selected:
        persona = PERSONAS[persona_id]
        try:
            item = _complete_json(
                client,
                _persona_messages(persona, context),
                thinking=thinking,
                label=f"persona:{persona_id}",
            )
            reactions.append(_reaction_from_vlm(persona, item, context))
            used_vlm = True
        except Exception as exc:
            logger.warning(
                "creative_panel_persona_fallback",
                ad_id=context.ad_id,
                persona_id=persona_id,
                error=str(exc),
            )
            reactions.append(fallback_by_id[persona_id])
            used_fallback = True

    try:
        summary_payload = _complete_json(
            client,
            _summary_messages(context, reactions),
            thinking=thinking,
            label="moderator_summary",
        )
        moderator_summary = _summary_from_vlm(summary_payload)
        used_vlm = True
    except Exception as exc:
        logger.warning(
            "creative_panel_summary_fallback",
            ad_id=context.ad_id,
            error=str(exc),
        )
        moderator_summary = fallback_summary
        used_fallback = True

    if not used_vlm:
        raise ValueError("all VLM creative panel calls failed")
    return reactions, moderator_summary, used_fallback


def _complete_json(
    client: AgentClient,
    messages: list[dict[str, str]],
    *,
    thinking: bool,
    label: str,
) -> dict[str, Any]:
    message = client.complete(messages, enable_thinking=thinking)
    raw = message.content or ""
    if not raw.strip():
        raise ValueError(f"{label} VLM response was empty")
    try:
        parsed = json.loads(_extract_json_object(raw))
    except (json.JSONDecodeError, ValueError) as exc:
        if message.finish_reason == "length":
            raise ValueError(f"{label} VLM response hit token limit before valid JSON") from exc
        raise
    if not isinstance(parsed, dict):
        raise ValueError(f"{label} VLM response must be a JSON object")
    return parsed


def _persona_messages(persona: Persona, context: _PanelContext) -> list[dict[str, str]]:
    evidence = _compact_evidence(context)
    schema = {
        "persona_id": persona.id,
        "first_impression": "max 18 words",
        "understood_product_or_offer": "max 18 words",
        "emotional_reaction": "max 10 words, qualitative only",
        "trust_points": ["max 2 items"],
        "confusion_points": ["max 2 items"],
        "likely_objection": "max 16 words",
        "memorable_moment": "max 12 words",
        "cta_likelihood": "max 14 words, no probability",
        "citation_ids": ["c0"],
    }
    system = (
        "You are ARGUS Creative Review Panel, a local-first ad analysis assistant. "
        "Simulate the requested persona's evaluation lens, not a real demographic sample. "
        "Internally reason from the supplied ad evidence before answering: identify what is "
        "clearly communicated, what is missing or ambiguous, which citation supports the read, "
        "and the likely objection from this persona lens. Do not reveal chain-of-thought. "
        "Use only supplied evidence; if evidence is missing, say unclear instead of filling gaps. "
        "Do not stereotype, infer protected traits, invent offers/prices/CTAs, make policy claims, "
        "or forecast market response, sales lift, or percentages. Observation tags are descriptive, "
        "not violations. Ignore repetitive OCR boilerplate unless it affects message clarity. "
        "Cite only supplied citation ids. Return one compact JSON object only."
    )
    user = (
        f"Persona: {persona.label}\nLens: {persona.lens}\n\n"
        f"Evidence:\n{json.dumps(evidence, ensure_ascii=True, separators=(',', ':'))}\n\n"
        "Return strict JSON with this exact shape and short values:\n"
        f"{json.dumps(schema, ensure_ascii=True, separators=(',', ':'))}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _summary_messages(
    context: _PanelContext,
    reactions: list[PersonaReaction],
) -> list[dict[str, str]]:
    reaction_brief = [
        {
            "persona_id": reaction.persona_id,
            "first_impression": reaction.first_impression,
            "objection": reaction.likely_objection,
            "confusion": reaction.confusion_points[:2],
        }
        for reaction in reactions
    ]
    schema = {
        "consensus": ["max 3 items"],
        "disagreements": ["max 2 items"],
        "message_clarity_issues": ["max 3 items"],
        "strongest_hooks": ["max 3 items"],
        "suggested_ab_variants": ["max 3 items"],
    }
    system = (
        "You are ARGUS Creative Review Panel moderator. Internally compare the independent "
        "persona reactions against the supplied evidence, then summarize only the evidence-backed "
        "consensus, disagreements, clarity issues, hooks, and A/B variants. Do not reveal "
        "chain-of-thought. Use only supplied reactions and evidence. No market forecasts, "
        "percentages, policy claims, or claims of representativeness. Return compact JSON only."
    )
    payload = {
        "ad_id": context.ad_id,
        "evidence": _compact_evidence(context),
        "persona_reactions": reaction_brief,
    }
    user = (
        f"Summarize this simulated panel:\n{json.dumps(payload, ensure_ascii=True, separators=(',', ':'))}\n\n"
        f"Return strict JSON with this shape:\n{json.dumps(schema, ensure_ascii=True, separators=(',', ':'))}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _compact_evidence(context: _PanelContext) -> dict[str, Any]:
    return {
        "ad_id": context.ad_id,
        "brand": context.brand,
        "category": context.category,
        "products": context.products[:4],
        "offers": context.offers[:4],
        "prices": context.prices[:3],
        "ctas": context.ctas[:3],
        "observation_tags": context.risk_labels[:4],
        "transcript": _truncate(context.transcript_text, 700),
        "ocr": [_truncate(text, 160) for text in _dedupe_text(context.ocr_texts)[:8]],
        "citations": _citation_payload(context.citations[:8]),
    }


def _citation_payload(citations: list[PanelCitation]) -> list[dict[str, Any]]:
    return [
        {
            "id": f"c{idx}",
            "time_ms": citation.time_ms,
            "frame_index": citation.frame_index,
            "source": citation.source,
            "text": _truncate(citation.text, 180),
        }
        for idx, citation in enumerate(citations)
    ]


def _reaction_from_vlm(
    persona: Persona,
    item: dict[str, Any],
    context: _PanelContext,
) -> PersonaReaction:
    citations = _citations_from_ids(item.get("citation_ids"), context)
    if not citations:
        citations = context.citations[:4]
    return PersonaReaction(
        persona_id=persona.id,
        persona_label=persona.label,
        lens=persona.lens,
        first_impression=_required_str(item, "first_impression"),
        understood_product_or_offer=_required_str(item, "understood_product_or_offer"),
        emotional_reaction=_required_str(item, "emotional_reaction"),
        trust_points=_str_list(item.get("trust_points"))[:6],
        confusion_points=_str_list(item.get("confusion_points"))[:6],
        likely_objection=_required_str(item, "likely_objection"),
        memorable_moment=_required_str(item, "memorable_moment"),
        cta_likelihood=_required_str(item, "cta_likelihood"),
        citations=citations[:6],
    )


def _summary_from_vlm(raw: Any) -> ModeratorSummary:
    if not isinstance(raw, dict):
        raise ValueError("missing moderator_summary")
    return ModeratorSummary(
        consensus=_str_list(raw.get("consensus"))[:6],
        disagreements=_str_list(raw.get("disagreements"))[:6],
        message_clarity_issues=_str_list(raw.get("message_clarity_issues"))[:6],
        strongest_hooks=_str_list(raw.get("strongest_hooks"))[:6],
        suggested_ab_variants=_str_list(raw.get("suggested_ab_variants"))[:6],
    )


def _citations_from_ids(raw: Any, context: _PanelContext) -> list[PanelCitation]:
    if not isinstance(raw, list):
        return []
    by_id = {f"c{idx}": citation for idx, citation in enumerate(context.citations[:12])}
    citations: list[PanelCitation] = []
    seen: set[str] = set()
    for value in raw:
        citation_id = str(value)
        if citation_id in by_id and citation_id not in seen:
            citations.append(by_id[citation_id])
            seen.add(citation_id)
    return citations


def _required_str(item: dict[str, Any], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing {key}")
    return value.strip()


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _dedupe_text(values: list[str]) -> list[str]:
    seen: set[str] = set()
    results: list[str] = []
    for raw in values:
        text = " ".join(str(raw).split())
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            results.append(text)
    return results


def _truncate(value: str | None, max_chars: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_chars:
        return text
    return f"{text[: max_chars - 1].rstrip()}..."


def _extract_json_object(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :]
        closing = text.rfind("```")
        if closing != -1:
            text = text[:closing]
    start = text.find("{")
    if start == -1:
        raise ValueError("VLM response did not contain JSON")
    depth = 0
    in_string = False
    escape = False
    for idx, ch in enumerate(text[start:], start):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : idx + 1]
    raise ValueError("VLM response JSON was incomplete")


def _reaction(persona: Persona, context: _PanelContext) -> PersonaReaction:
    product = _product_phrase(context)
    offer = _offer_phrase(context)
    cta = _cta_phrase(context)
    citations = context.citations[:4]
    memorable = citations[0].text if citations else product

    trust_points = _trust_points(persona.id, context)
    confusion_points = _confusion_points(persona.id, context)

    return PersonaReaction(
        persona_id=persona.id,
        persona_label=persona.label,
        lens=persona.lens,
        first_impression=_first_impression(persona.id, context, product),
        understood_product_or_offer=(
            f"The ad appears to promote {product}. {offer}".strip()
            if product
            else f"The product is not fully clear from the stored evidence. {offer}".strip()
        ),
        emotional_reaction=_emotional_reaction(persona.id, context),
        trust_points=trust_points,
        confusion_points=confusion_points,
        likely_objection=_likely_objection(persona.id, context),
        memorable_moment=memorable,
        cta_likelihood=_cta_likelihood(cta, offer),
        citations=citations,
    )


def _first_impression(persona_id: str, context: _PanelContext, product: str) -> str:
    brand = context.brand or "the advertiser"
    if persona_id == "luxury_shopper":
        return (
            f"{brand} needs premium cues to land quickly; the stored evidence reads as {product}."
        )
    if persona_id == "gen_z_mobile_viewer":
        return f"The ad has to communicate fast; the clearest takeaway is {product}."
    if persona_id == "compliance_reviewer":
        return f"The creative is understandable as {product}, with terms that need evidence-backed clarity."
    return f"The ad reads as a {brand} message for {product}."


def _emotional_reaction(persona_id: str, context: _PanelContext) -> str:
    has_offer = bool(context.offers or context.prices)
    has_risk = bool(context.risk_labels)
    if persona_id == "budget_parent":
        return (
            "Value-oriented interest." if has_offer else "Interested, but waiting for cost clarity."
        )
    if persona_id == "skeptical_buyer":
        return "Cautious curiosity." if has_risk else "Open but proof-seeking."
    if persona_id == "luxury_shopper":
        return "Aspirational if the visuals feel premium; otherwise neutral."
    if persona_id == "first_time_car_buyer":
        return "Encouraged by concrete financing or model details." if has_offer else "Uncertain."
    if persona_id == "gen_z_mobile_viewer":
        return "Quick interest if the hook appears in the first shot."
    return "Attentive to qualifiers and claim boundaries."


def _trust_points(persona_id: str, context: _PanelContext) -> list[str]:
    points: list[str] = []
    if context.brand:
        points.append(f"Recognizable brand cue: {context.brand}.")
    if context.prices:
        points.append(f"Concrete price or financing text: {context.prices[0]}.")
    if context.offers:
        points.append(f"Specific offer text: {context.offers[0]}.")
    if context.disclaimers and persona_id == "compliance_reviewer":
        points.append("Disclaimers are present for review.")
    return points or ["Stored evidence is limited, so trust depends on clearer claims and proof."]


def _confusion_points(persona_id: str, context: _PanelContext) -> list[str]:
    points: list[str] = []
    if not context.products:
        points.append("Product or service name is not explicit.")
    if not context.offers and not context.prices:
        points.append("The concrete offer or price is not explicit.")
    if not context.ctas:
        points.append("The next action is not explicit.")
    if context.disclaimers and persona_id in {"budget_parent", "skeptical_buyer"}:
        points.append("Offer terms may need simpler wording.")
    if context.risk_labels and persona_id in {"skeptical_buyer", "compliance_reviewer"}:
        points.append(f"Observation tags to review: {', '.join(context.risk_labels[:3])}.")
    return points or ["Main message is clear from the stored evidence."]


def _likely_objection(persona_id: str, context: _PanelContext) -> str:
    if persona_id == "budget_parent" and not context.prices:
        return "I need the real total cost before I would act."
    if persona_id == "skeptical_buyer" and context.risk_labels:
        return "I need proof for the strongest claim before trusting it."
    if persona_id == "luxury_shopper":
        return "The ad must make the product feel distinctive, not just discounted."
    if persona_id == "first_time_car_buyer":
        return "I need clearer terms, model details, and what happens after clicking."
    if persona_id == "gen_z_mobile_viewer" and not context.ctas:
        return "I may understand the message but not know what to do next."
    if persona_id == "compliance_reviewer" and context.disclaimers:
        return "Terms need to be readable and matched to the claim they qualify."
    return "I need one clearer reason to act now."


def _cta_likelihood(cta: str, offer: str) -> str:
    if cta and offer:
        return "Likely to consider the CTA if already in-market; not a forecast."
    if cta:
        return "CTA is visible, but motivation depends on message clarity."
    return "CTA intent is unclear because no direct next step was extracted."


def _moderator_summary(
    context: _PanelContext,
    reactions: list[PersonaReaction],
) -> ModeratorSummary:
    clarity_issues = sorted(
        {point for reaction in reactions for point in reaction.confusion_points}
    )
    strongest_hooks = []
    if context.offers:
        strongest_hooks.append(context.offers[0])
    if context.prices:
        strongest_hooks.append(context.prices[0])
    if context.ctas:
        strongest_hooks.append(context.ctas[0])
    if not strongest_hooks and context.citations:
        strongest_hooks.append(context.citations[0].text)

    variants = []
    if context.offers or context.prices:
        variants.append("Test an offer-first opening against a brand-first opening.")
    if context.ctas:
        variants.append("Test the current CTA against a more specific next-step CTA.")
    if context.disclaimers:
        variants.append("Test simplified terms placement near the qualified claim.")
    if not variants:
        variants.append("Test a clearer product-and-CTA end card.")

    return ModeratorSummary(
        consensus=[
            f"Panel reactions are grounded to ad_id {context.ad_id}.",
            "The clearest message elements are strongest when tied to extracted offer, price, or CTA evidence.",
        ],
        disagreements=[
            "Value-oriented personas prioritize cost clarity; premium-oriented personas prioritize brand distinctiveness."
        ],
        message_clarity_issues=clarity_issues[:6],
        strongest_hooks=strongest_hooks[:5],
        suggested_ab_variants=variants[:5],
    )


def _collect_citations(
    ad_id: str,
    classification: ClassificationRecord | None,
    marketing: MarketingEntities,
    ocr_items: list[_OCRItem],
    transcript_text: str,
) -> list[PanelCitation]:
    citations: list[PanelCitation] = []
    for entity in [*marketing.offers, *marketing.prices, *marketing.ctas, *marketing.disclaimers]:
        for evidence in entity.evidence:
            citations.append(_citation_from_evidence(ad_id, evidence))
    if classification:
        for evidence in classification.evidence:
            citations.append(_citation_from_evidence(ad_id, evidence))
    for item in ocr_items[:3]:
        citations.append(
            PanelCitation(
                ad_id=ad_id,
                time_ms=item.time_ms,
                frame_index=item.frame_index,
                source=item.engine,
                text=item.text,
            )
        )
    if transcript_text:
        citations.append(
            PanelCitation(
                ad_id=ad_id,
                time_ms=None,
                frame_index=None,
                source="transcript",
                text=transcript_text[:240],
            )
        )
    return _dedupe_citations(citations)


def _citation_from_evidence(ad_id: str, evidence: EvidenceItem) -> PanelCitation:
    return PanelCitation(
        ad_id=ad_id,
        time_ms=evidence.time_ms,
        frame_index=evidence.frame_index,
        source=evidence.source,
        text=evidence.text,
    )


def _dedupe_citations(citations: list[PanelCitation]) -> list[PanelCitation]:
    seen: set[tuple[str, int | None, int | None, str]] = set()
    results: list[PanelCitation] = []
    for citation in citations:
        key = (
            citation.source,
            citation.time_ms,
            citation.frame_index,
            citation.text.strip().lower(),
        )
        if citation.text.strip() and key not in seen:
            seen.add(key)
            results.append(citation)
    return results[:12]


def _transcript_text(conn: sqlite3.Connection, ad_id: str) -> str:
    rows = conn.execute(
        """
        SELECT text
        FROM transcript_segments
        WHERE ad_id = ?
        ORDER BY start_ms, id
        """,
        (ad_id,),
    ).fetchall()
    return " ".join(str(row["text"]).strip() for row in rows if row["text"]).strip()


def _ocr_items(conn: sqlite3.Connection, ad_id: str) -> list[_OCRItem]:
    rows = conn.execute(
        """
        SELECT f.time_ms, f.frame_index, o.engine, o.text
        FROM frames f
        JOIN ocr_items o ON o.frame_id = f.id
        WHERE f.ad_id = ?
        ORDER BY f.frame_index, o.id
        """,
        (ad_id,),
    ).fetchall()
    return [
        _OCRItem(
            time_ms=int(row["time_ms"]),
            frame_index=int(row["frame_index"]),
            engine=str(row["engine"]),
            text=str(row["text"]),
        )
        for row in rows
        if str(row["text"]).strip()
    ]


def _products(products_text: str | None, marketing: MarketingEntities) -> list[str]:
    if products_text:
        return [part.strip() for part in products_text.split(",") if part.strip()]
    return marketing.products


def _product_phrase(context: _PanelContext) -> str:
    if context.products:
        return ", ".join(context.products[:3])
    if context.category:
        return f"{context.category} offer"
    return "the advertised product or service"


def _offer_phrase(context: _PanelContext) -> str:
    parts = [*context.offers[:2], *context.prices[:2]]
    if not parts:
        return "No concrete offer was extracted."
    return f"Extracted offer cues: {'; '.join(parts)}."


def _cta_phrase(context: _PanelContext) -> str:
    return context.ctas[0] if context.ctas else ""


def _evidence_sources(context: _PanelContext) -> list[str]:
    sources = {citation.source for citation in context.citations}
    if context.marketing.products or context.marketing.offers or context.marketing.ctas:
        sources.add("marketing_entities")
    if context.classification:
        sources.add("classification")
    return sorted(sources)
