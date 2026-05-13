from __future__ import annotations

import re
from collections.abc import Iterable

_ALIASES: dict[str, tuple[str, ...]] = {
    "car": ("automobile", "vehicle", "sedan"),
    "cars": ("automobiles", "vehicles"),
    "suv": ("sport utility vehicle", "vehicle"),
    "truck": ("pickup truck", "vehicle"),
    "phone": ("smartphone", "mobile phone", "app screen"),
    "app": ("mobile app", "smartphone screen", "user interface"),
    "doctor": ("medical professional", "clinic", "healthcare setting"),
    "candidate": ("political candidate", "campaign speaker", "podium"),
    "governor": ("political campaign", "candidate", "podium"),
    "discount": ("sale badge", "price callout", "offer graphic"),
    "price": ("price callout", "pricing text", "offer graphic"),
    "testimonial": ("person speaking to camera", "interview", "customer review"),
    "before after": ("comparison", "side by side", "transformation"),
}

_COLOR_OBJECT_RE = re.compile(
    r"\b(red|blue|green|black|white|silver|gray|grey|yellow|orange)\s+([a-z0-9_-]+)\b",
    flags=re.IGNORECASE,
)


def expand_visual_query_texts(query: str | None, *, limit: int = 6) -> list[str]:
    """Expand a visual phrase into a few cross-modal SigLIP query prompts.

    This intentionally stays small. Query-time embedding is interactive, and too
    many paraphrases can dilute a concrete request like "red car".
    """
    normalized = " ".join((query or "").strip().split())
    if not normalized:
        return []

    variants = [normalized]
    lowered = normalized.casefold()
    tokens = set(re.findall(r"[a-z0-9]+", lowered))

    for trigger, expansions in _ALIASES.items():
        trigger_tokens = set(trigger.split())
        if trigger in lowered or trigger_tokens.issubset(tokens):
            variants.extend(expansions)

    for color, noun in _COLOR_OBJECT_RE.findall(normalized):
        variants.extend(
            (
                f"{color} {noun}",
                f"{color} colored {noun}",
                f"{noun} in {color}",
            )
        )

    return _dedupe(variants)[:limit]


def mean_pool(vectors: Iterable[list[float]]) -> list[float] | None:
    rows = list(vectors)
    if not rows:
        return None
    dim = len(rows[0])
    return [sum(row[i] for row in rows) / len(rows) for i in range(dim)]


def _dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.casefold()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out
