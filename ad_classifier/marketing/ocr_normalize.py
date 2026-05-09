from __future__ import annotations

import re


def normalize_ocr_text(text: str) -> str:
    text = text.replace("％", "%")
    text = re.sub(r"\$(\d{1,3})\.(\d{3})(?!\d)", r"$\1,\2", text)
    text = re.sub(r"\bDickPoe\b", "Dick Poe", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(20\d{2})(?=JEEP)", r"\1 ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(20\d{2})(?=CHRYSLER)", r"\1 ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bJEEP(?=GRAND|WRANGLER|GLADIATOR)", "JEEP ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bCHRYSLER(?=PACIFICA)", "CHRYSLER ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bGRANDCHEROKEE\b", "GRAND CHEROKEE", text, flags=re.IGNORECASE)
    text = re.sub(r"\bCHRYSLERPACIFICA\b", "CHRYSLER PACIFICA", text, flags=re.IGNORECASE)
    text = re.sub(r"\bWRANGLER(?=4-DOOR)", "WRANGLER ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bLIMITED(?=4X4|4x4)", "LIMITED ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bPACIFICA(?=\$)", "PACIFICA ", text, flags=re.IGNORECASE)
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
