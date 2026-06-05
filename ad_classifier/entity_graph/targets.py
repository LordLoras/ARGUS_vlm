from __future__ import annotations

from urllib.parse import urlparse, urlunparse

from ad_classifier.entity_graph.models import SubmittedAdWebTarget


def from_ad_url_mapping(mapping: dict[str, list[str]]) -> list[SubmittedAdWebTarget]:
    targets: list[SubmittedAdWebTarget] = []
    seen: set[tuple[str, str]] = set()
    for raw_ad_id, urls in mapping.items():
        ad_id = raw_ad_id.strip()
        if not ad_id:
            continue
        for raw_url in urls:
            url = normalize_url(raw_url)
            if url is None:
                continue
            key = (ad_id, url.lower())
            if key in seen:
                continue
            seen.add(key)
            parsed = urlparse(url)
            targets.append(
                SubmittedAdWebTarget(
                    ad_id=ad_id,
                    url=url,
                    domain=parsed.netloc.lower(),
                    source="explicit_reference",
                    evidence_text="Explicit reference URL supplied to experimental crawler",
                )
            )
    return targets


def normalize_url(value: str) -> str | None:
    text = str(value or "").strip().strip('"').strip("'").strip()
    if not text:
        return None
    if not text.lower().startswith(("http://", "https://")):
        text = f"https://{text}"
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or "." not in parsed.netloc:
        return None
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path or "/",
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )
