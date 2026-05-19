import type { CampaignCount, CampaignResearch } from "../../lib/types";

export function buildSignalCards(research: CampaignResearch) {
  const product = research.messaging.top_products[0];
  const offer = research.messaging.top_offers[0];
  const cta = research.messaging.top_ctas[0];
  const risk = research.watchouts.risk_labels[0];
  return [
    {
      label: "Product mix",
      value: product?.value ?? "-",
      detail: product ? `${research.messaging.top_products.length} values detected` : "No product signal",
      items: research.messaging.top_products
    },
    {
      label: "Top offer",
      value: offer?.value ?? "-",
      detail: offer ? `${offer.count} ads` : "No offer signal"
    },
    {
      label: "Top CTA",
      value: cta?.value ?? "-",
      detail: cta ? `${cta.count} ads` : "No CTA signal"
    },
    {
      label: "Observations",
      value: risk?.value ?? "-",
      detail: risk ? `${risk.count} ads` : "No repeated tags"
    }
  ];
}

export function formatScore(value?: number | null) {
  return value == null ? "-" : value.toFixed(2);
}

export function formatRange(first?: string | null, last?: string | null) {
  const left = first ? first.slice(0, 10) : "";
  const right = last ? last.slice(0, 10) : "";
  if (left && right && left !== right) return `${left} - ${right}`;
  return left || right || "date range";
}

export function emptyResearch(adCount: number): CampaignResearch {
  const emptyCounts: CampaignCount[] = [];
  return {
    summary: {
      ad_count: adCount,
      user_assigned: 0,
      auto_assigned: 0,
      mean_similarity: null,
      avg_confidence: null,
      min_confidence: null,
      first_seen: null,
      last_seen: null,
      span_days: null,
      brands: emptyCounts,
      advertisers: emptyCounts,
      categories: emptyCounts,
      subcategories: emptyCounts
    },
    messaging: {
      top_products: emptyCounts,
      product_families: [],
      top_offers: emptyCounts,
      top_ctas: emptyCounts,
      top_prices: emptyCounts,
      campaign_signals: emptyCounts
    },
    creative: {
      runtime_buckets: [],
      aspect_ratios: emptyCounts,
      formats: emptyCounts,
      voiceover_ads: 0,
      on_screen_text_ads: 0,
      disclaimer_ads: 0,
      small_print_ads: 0,
      disclaimer_density: emptyCounts
    },
    watchouts: {
      risk_labels: emptyCounts,
      disclaimer_count: 0,
      small_print_count: 0,
      low_confidence_ads: []
    },
    insights: [],
    research_prompts: []
  };
}
