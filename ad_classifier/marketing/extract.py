from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import parse_qsl, urlparse

from ad_classifier.ingest.models import WhisperTranscript
from ad_classifier.marketing.commercial import (
    extract_commercial_entities,
    merge_commercial_entities,
    normalize_ocr_text,
    repair_products,
)
from ad_classifier.models.common import EvidenceItem
from ad_classifier.models.marketing import (
    ContactPoints,
    LandingPageEntity,
    MarketingEntities,
    OfferTerms,
    PhoneNumberEntity,
    PromoCodeEntity,
    QRCodeEntity,
    SocialHandleEntity,
    WebsiteEntity,
)
from ad_classifier.pipeline.ocr.models import OCRItem

_URL_PATTERN = re.compile(
    r"\b(?:https?://)?(?:www\.)?[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"(?:\.[a-z]{2,})(?:/[^\s\"'<>)]*)?",
    re.IGNORECASE,
)
_PHONE_PATTERN = re.compile(r"\b(?:\+?1[\s.()-]*)?(?:\(?\d{3}\)?[\s.()-]*)\d{3}[\s.()-]*\d{4}\b")
_VANITY_PHONE_PATTERN = re.compile(
    r"\b(?:1[\s.-]*)?(?:800|888|877|866|855|844|833)[\s.-]*[A-Z0-9]{3,}" r"[\s.-]*[A-Z0-9]{4}\b",
    re.IGNORECASE,
)
_HANDLE_PATTERN = re.compile(r"(?<![\w.])@([a-z0-9_.]{2,30})", re.IGNORECASE)
_PROMO_CODE_PATTERN = re.compile(
    r"\b(?:use\s+)?(?:promo|coupon|discount|offer)?\s*code[:\s]+([A-Z0-9][A-Z0-9-]{2,20})\b",
    re.IGNORECASE,
)
_SOCIAL_DOMAINS = {
    "facebook": "facebook",
    "fb": "facebook",
    "instagram": "instagram",
    "tiktok": "tiktok",
    "youtube": "youtube",
    "youtu": "youtube",
    "twitter": "x",
    "x": "x",
    "linkedin": "linkedin",
    "pinterest": "pinterest",
    "snapchat": "snapchat",
}
_SCARCITY_TERMS = ("while supplies last", "limited quantities", "limited supply", "only left")
_URGENCY_TERMS = ("limited time", "today only", "ends soon", "call today", "now", "hurry")
_MIN_TRACKING_CONFIDENCE = 0.75


def extract_tracking_entities(
    *,
    ocr_items: Iterable[OCRItem],
    transcript: WhisperTranscript,
) -> MarketingEntities:
    evidence_items = _evidence_from_sources(ocr_items, transcript)
    entities = MarketingEntities(contact_points=ContactPoints(), offer_terms=OfferTerms())
    contact_points = entities.contact_points
    offer_terms = entities.offer_terms

    seen_urls: set[str] = set()
    seen_phones: set[str] = set()
    seen_handles: set[tuple[str, str | None, str | None]] = set()
    seen_codes: set[str] = set()

    for evidence in evidence_items:
        text = normalize_ocr_text(evidence.text)
        normalized_evidence = evidence.model_copy(update={"text": text})
        if not _is_reliable_tracking_evidence(evidence):
            continue

        for raw_url in _URL_PATTERN.findall(text):
            website = _website_from_match(raw_url, normalized_evidence)
            if website is None or website.url in seen_urls:
                continue
            seen_urls.add(website.url)
            contact_points.websites.append(website)

            platform = _platform_from_domain(website.domain)
            if platform:
                handle = _handle_from_social_url(website.url)
                key = (platform, handle, website.url)
                if key not in seen_handles:
                    seen_handles.add(key)
                    contact_points.social_handles.append(
                        SocialHandleEntity(
                            platform=platform,
                            handle=handle,
                            url=website.url,
                            evidence=[normalized_evidence],
                        )
                    )

        for raw_phone in _PHONE_PATTERN.findall(text):
            phone = _phone_entity(raw_phone, normalized_evidence, phone_type="phone")
            key = phone.normalized or phone.raw
            if key not in seen_phones:
                seen_phones.add(key)
                contact_points.phone_numbers.append(phone)

        for raw_phone in _VANITY_PHONE_PATTERN.findall(text):
            phone = _phone_entity(raw_phone, normalized_evidence, phone_type="vanity")
            key = phone.normalized or phone.raw
            if key not in seen_phones:
                seen_phones.add(key)
                contact_points.phone_numbers.append(phone)

        for handle in _HANDLE_PATTERN.findall(text):
            key = ("other", handle, None)
            if key not in seen_handles:
                seen_handles.add(key)
                contact_points.social_handles.append(
                    SocialHandleEntity(platform="other", handle=handle, evidence=[normalized_evidence])
                )

        for code in _PROMO_CODE_PATTERN.findall(text):
            normalized = code.upper()
            if normalized not in seen_codes:
                seen_codes.add(normalized)
                offer_terms.promo_codes.append(
                    PromoCodeEntity(code=normalized, raw_text=code, evidence=[normalized_evidence])
                )

        lower = text.lower()
        if "qr" in lower and "code" in lower:
            contact_points.qr_codes.append(
                QRCodeEntity(
                    present=True,
                    destination_hint="visible QR code",
                    evidence=[normalized_evidence],
                )
            )
        for term in _SCARCITY_TERMS:
            if term in lower and term not in offer_terms.scarcity_signals:
                offer_terms.scarcity_signals.append(term)
        for term in _URGENCY_TERMS:
            if term in lower and term not in offer_terms.urgency_signals:
                offer_terms.urgency_signals.append(term)

    landing_page = _landing_page_from_websites(contact_points.websites)
    entities.landing_page = landing_page
    return merge_commercial_entities(entities, extract_commercial_entities(evidence_items))


def enrich_marketing_entities(
    base: MarketingEntities,
    *,
    ocr_items: Iterable[OCRItem],
    transcript: WhisperTranscript,
) -> MarketingEntities:
    """Repair VLM entities with cheap deterministic OCR/transcript extraction."""
    base.products = repair_products(base.products, base.brand.name or base.advertiser.brand_name)
    extracted = extract_tracking_entities(ocr_items=ocr_items, transcript=transcript)
    return merge_tracking_entities(base, extracted)


def merge_tracking_entities(
    base: MarketingEntities, extracted: MarketingEntities
) -> MarketingEntities:
    base = merge_commercial_entities(base, extracted)

    for website in extracted.contact_points.websites:
        existing_urls = {item.url for item in base.contact_points.websites}
        existing_domains = {
            item.domain for item in base.contact_points.websites if item.domain is not None
        }
        if website.url not in existing_urls and not _is_weaker_suffix_domain(
            website.domain,
            existing_domains,
        ):
            base.contact_points.websites.append(website)

    for phone in extracted.contact_points.phone_numbers:
        key = phone.normalized or phone.raw
        existing = {item.normalized or item.raw for item in base.contact_points.phone_numbers}
        if key not in existing:
            base.contact_points.phone_numbers.append(phone)

    for handle in extracted.contact_points.social_handles:
        key = (handle.platform, handle.handle, handle.url)
        existing = {
            (item.platform, item.handle, item.url) for item in base.contact_points.social_handles
        }
        if key not in existing:
            base.contact_points.social_handles.append(handle)

    for qr_code in extracted.contact_points.qr_codes:
        if not base.contact_points.qr_codes:
            base.contact_points.qr_codes.append(qr_code)

    for promo_code in extracted.offer_terms.promo_codes:
        existing = {item.code for item in base.offer_terms.promo_codes}
        if promo_code.code not in existing:
            base.offer_terms.promo_codes.append(promo_code)

    base.offer_terms.scarcity_signals = _merge_strings(
        base.offer_terms.scarcity_signals,
        extracted.offer_terms.scarcity_signals,
    )
    base.offer_terms.urgency_signals = _merge_strings(
        base.offer_terms.urgency_signals,
        extracted.offer_terms.urgency_signals,
    )

    if base.landing_page.url is None:
        base.landing_page = extracted.landing_page
    if base.advertiser.brand_name is None:
        base.advertiser.brand_name = base.brand.name
    return base


def _evidence_from_sources(
    ocr_items: Iterable[OCRItem],
    transcript: WhisperTranscript,
) -> list[EvidenceItem]:
    ocr_list = list(ocr_items)
    evidence: list[EvidenceItem] = [
        EvidenceItem(
            time_ms=item.time_ms,
            frame_index=item.frame_index,
            source="ocr",
            text=item.text,
            bbox=item.bbox,
            confidence=item.confidence,
        )
        for item in ocr_list
        if item.text
    ]
    evidence.extend(_joined_ocr_evidence(ocr_list))
    evidence.extend(
        EvidenceItem(
            time_ms=segment.start_ms,
            source="transcript",
            text=segment.text,
            confidence=segment.confidence,
        )
        for segment in transcript.segments
        if segment.text
    )
    return evidence


def _joined_ocr_evidence(ocr_items: list[OCRItem]) -> list[EvidenceItem]:
    by_frame: dict[int, list[OCRItem]] = {}
    for item in ocr_items:
        if item.text:
            by_frame.setdefault(item.frame_index, []).append(item)

    joined: list[EvidenceItem] = []
    for frame_index, frame_items in by_frame.items():
        if len(frame_items) < 2:
            continue
        text = normalize_ocr_text(" ".join(item.text for item in frame_items if item.text))
        if not text:
            continue
        confidences = [item.confidence for item in frame_items if item.confidence is not None]
        confidence = sum(confidences) / len(confidences) if confidences else None
        joined.append(
            EvidenceItem(
                time_ms=frame_items[0].time_ms,
                frame_index=frame_index,
                source="ocr",
                text=text,
                confidence=confidence,
                reason="joined OCR frame text",
            )
        )
    return joined


def _website_from_match(raw_url: str, evidence: EvidenceItem) -> WebsiteEntity | None:
    raw_url = raw_url.rstrip(".,;:")
    url = raw_url if raw_url.lower().startswith(("http://", "https://")) else f"https://{raw_url}"
    parsed = urlparse(url)
    domain = parsed.netloc.lower().removeprefix("www.")
    if not domain or "." not in domain:
        return None
    return WebsiteEntity(url=url, domain=domain, display_text=raw_url, evidence=[evidence])


def _phone_entity(raw_phone: str, evidence: EvidenceItem, *, phone_type: str) -> PhoneNumberEntity:
    digits = "".join(ch for ch in raw_phone if ch.isdigit())
    normalized = None
    if len(digits) == 10:
        normalized = f"+1{digits}"
    elif len(digits) == 11 and digits.startswith("1"):
        normalized = f"+{digits}"
    return PhoneNumberEntity(
        raw=raw_phone.strip(),
        normalized=normalized,
        type=phone_type,
        evidence=[evidence],
    )


def _platform_from_domain(domain: str | None) -> str | None:
    if not domain:
        return None
    parts = domain.lower().split(".")
    if not parts:
        return None
    return _SOCIAL_DOMAINS.get(parts[-2] if len(parts) >= 2 else parts[0])


def _handle_from_social_url(url: str) -> str | None:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    return parts[0].lstrip("@") if parts else None


def _landing_page_from_websites(websites: list[WebsiteEntity]) -> LandingPageEntity:
    if not websites:
        return LandingPageEntity()
    first = websites[0]
    parsed = urlparse(first.url)
    utm_params = {
        key: value for key, value in parse_qsl(parsed.query) if key.lower().startswith("utm_")
    }
    return LandingPageEntity(
        url=first.url,
        domain=first.domain,
        path=parsed.path or None,
        utm_params=utm_params,
        evidence=list(first.evidence),
    )


def _merge_strings(left: list[str], right: list[str]) -> list[str]:
    merged = list(left)
    for item in right:
        if item and item not in merged:
            merged.append(item)
    return merged


def _is_reliable_tracking_evidence(evidence: EvidenceItem) -> bool:
    return evidence.confidence is None or evidence.confidence >= _MIN_TRACKING_CONFIDENCE


def _is_weaker_suffix_domain(domain: str | None, existing_domains: set[str]) -> bool:
    if not domain:
        return False
    return any(existing != domain and existing.endswith(domain) for existing in existing_domains)
