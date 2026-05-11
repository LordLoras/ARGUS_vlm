from __future__ import annotations

import re
from pathlib import Path

import yaml

_BRAND_RULES_PATH = Path(__file__).parent.parent.parent / "brand_ocr_normalize.yaml"

_BRAND_RULES: list[tuple[re.Pattern[str], str]] | None = None


def _load_brand_rules() -> list[tuple[re.Pattern[str], str]]:
    global _BRAND_RULES
    if _BRAND_RULES is not None:
        return _BRAND_RULES
    _BRAND_RULES = []
    try:
        data = yaml.safe_load(_BRAND_RULES_PATH.read_text(encoding="utf-8")) or {}
        for entry in data.get("rules", []):
            pattern_str = entry.get("pattern")
            replacement = entry.get("replacement", "")
            if pattern_str:
                _BRAND_RULES.append((re.compile(pattern_str, re.IGNORECASE), replacement))
    except FileNotFoundError:
        pass
    return _BRAND_RULES


def normalize_ocr_text(text: str) -> str:
    text = text.replace("％", "%")
    text = re.sub(r"\$(\d{1,3})\.(\d{3})(?!\d)", r"$\1,\2", text)

    for pattern, replacement in _load_brand_rules():
        text = pattern.sub(replacement, text)

    text = re.sub(r"\bBELOWMSRP\b", "BELOW MSRP", text, flags=re.IGNORECASE)
    text = re.sub(r"\bREBAT\b", "REBATE", text, flags=re.IGNORECASE)
    text = re.sub(r"\bMILITARY&FIRSTRESPONDER\b", "MILITARY & FIRST RESPONDER", text, flags=re.IGNORECASE)
    text = re.sub(r"\bFIRSTRESPONDER\b", "FIRST RESPONDER", text, flags=re.IGNORECASE)
    text = re.sub(r"\bONSELECT\b", "ON SELECT", text, flags=re.IGNORECASE)
    text = re.sub(r"\bOffersexclude\b", "Offers exclude", text, flags=re.IGNORECASE)
    text = re.sub(r"\bAPRfinancing\b", "APR financing", text, flags=re.IGNORECASE)
    text = re.sub(r"\bDUEAT\b", "DUE AT", text, flags=re.IGNORECASE)
    text = re.sub(r"\bLEASEDETAILS\b", "LEASE DETAILS", text, flags=re.IGNORECASE)
    text = re.sub(r"\bCALL(?=\d)", "CALL ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(\d{1,3})MOS\b", r"\1 MOS", text, flags=re.IGNORECASE)
    text = re.sub(r"(?<=[a-z])\.(?=[A-Z0-9])", ". ", text)
    text = re.sub(r"(?<=\d)\.(?=[A-Z])", ". ", text)
    return re.sub(r"\s+", " ", text).strip()
