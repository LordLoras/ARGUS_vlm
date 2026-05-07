import type { EvidenceItem } from "./types";

type PriceLike = {
  text?: string | null;
  amount?: number | null;
  currency?: string | null;
  evidence?: EvidenceItem[];
};

export function formatPrice(price: PriceLike, context?: string | null) {
  if (price.amount != null) {
    const amount = Number.isInteger(price.amount)
      ? price.amount.toFixed(0)
      : price.amount.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
    return `${displayCurrency(price.currency)}${amount}`;
  }
  if (price.text?.trim()) return price.text;
  const contextPrice = context?.match(/[$€£]\s?\d[\d,.]*/)?.[0];
  if (contextPrice) return contextPrice.replace(/\s+/g, "");
  return "Price mentioned";
}

export function priceContext(price: PriceLike, evidenceItems: EvidenceItem[] = []) {
  const ownEvidence = price.evidence?.[0];
  const timeMs = ownEvidence?.time_ms;
  const priceLabel = formatPrice(price);
  const tokens = priceTokens(price, priceLabel === "Price mentioned" ? "" : priceLabel);

  if (timeMs != null) {
    const nearby = evidenceItems
      .filter((item) => item.text && item.time_ms != null)
      .filter((item) => Math.abs(Number(item.time_ms) - timeMs) <= 1500)
      .filter((item) => !tokens.length || hasAnyToken(item.text ?? "", tokens));
    const candidate = nearby
      .sort(
        (left, right) =>
          Math.abs(Number(left.time_ms) - timeMs) - Math.abs(Number(right.time_ms) - timeMs)
      )
      .find((item) => isMoreContextual(item.text ?? "", priceLabel));
    if (candidate?.text) return candidate.text;
  }

  if (ownEvidence?.text && isMoreContextual(ownEvidence.text, priceLabel)) {
    return ownEvidence.text;
  }
  return null;
}

function priceTokens(price: PriceLike, priceLabel: string) {
  return [
    priceLabel,
    price.text,
    price.amount != null ? String(price.amount) : null,
    price.amount != null ? String(Math.trunc(price.amount)) : null
  ].filter((value): value is string => Boolean(value && normalize(value).length > 0));
}

function hasAnyToken(text: string, tokens: string[]) {
  const normalizedText = normalize(text);
  return tokens.some((token) => normalizedText.includes(normalize(token)));
}

function isMoreContextual(text: string, priceLabel: string) {
  return normalize(text) !== normalize(priceLabel) && text.trim().length > priceLabel.trim().length + 2;
}

function normalize(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "");
}

function displayCurrency(currency?: string | null) {
  const normalized = (currency ?? "$").trim().toUpperCase();
  if (normalized === "USD" || normalized === "US$" || normalized === "$") return "$";
  return currency ?? "$";
}
