from __future__ import annotations

import re
from collections.abc import Iterable

DEFAULT_AD_SEARCH_COLUMNS = (
    "id",
    "brand_name",
    "advertiser_name",
    "products_text",
    "primary_category",
    "website_domain",
    "phone_number",
    "landing_page_domain",
)

_HVAC_TERMS = (
    "hvac",
    "heating",
    "cooling",
    "air conditioning",
    "air conditioner",
    "furnace",
    "ventilation",
)

_SERVICE_TERMS = (
    "service",
    "services",
    "repair",
    "repairs",
    "install",
    "installation",
    "installations",
    "maintenance",
    "contractor",
    "contractors",
    "estimate",
    "quote",
    "appointment",
    "heating",
    "cooling",
    "air conditioning",
    "plumbing",
    "roofing",
    "electrical",
    "pest control",
    "lawn care",
    "cleaning",
)

_AUTOMOTIVE_TERMS = (
    "automotive",
    "auto",
    "car",
    "cars",
    "vehicle",
    "vehicles",
    "truck",
    "trucks",
    "suv",
    "suvs",
    "dealer",
    "dealership",
)

_FOOD_TERMS = (
    "food_beverage",
    "food",
    "foods",
    "restaurant",
    "restaurants",
    "pizza",
    "coffee",
    "drink",
    "drinks",
    "beverage",
    "beverages",
    "meal",
    "meals",
)

_HEALTH_TERMS = (
    "health_wellness",
    "health",
    "medical",
    "doctor",
    "doctors",
    "clinic",
    "dental",
    "dentist",
    "dentists",
    "wellness",
    "pharmacy",
    "pharmacies",
    "prescription",
    "fitness",
)

_FINANCE_TERMS = (
    "finance_banking",
    "finance",
    "financial",
    "bank",
    "banking",
    "loan",
    "loans",
    "credit",
    "mortgage",
    "insurance",
    "apr",
    "financing",
)

_RETAIL_TERMS = (
    "retail_ecommerce",
    "retail",
    "ecommerce",
    "e-commerce",
    "shop",
    "shopping",
    "store",
    "stores",
    "sale",
    "deal",
    "discount",
)

_TRAVEL_TERMS = (
    "travel_hospitality",
    "travel",
    "hotel",
    "hotels",
    "flight",
    "flights",
    "vacation",
    "resort",
    "cruise",
    "booking",
)

_EDUCATION_TERMS = (
    "education",
    "school",
    "schools",
    "college",
    "university",
    "course",
    "courses",
    "training",
    "degree",
)

_REAL_ESTATE_TERMS = (
    "real_estate",
    "real estate",
    "home",
    "homes",
    "house",
    "houses",
    "apartment",
    "apartments",
    "rent",
    "rental",
    "realtor",
)

_ENTERTAINMENT_TERMS = (
    "streaming_entertainment",
    "streaming",
    "entertainment",
    "movie",
    "movies",
    "show",
    "shows",
    "series",
    "music",
    "concert",
)

_APPS_GAMES_TERMS = (
    "mobile_apps_games",
    "app",
    "apps",
    "game",
    "games",
    "mobile",
    "download",
)

_ALIASES: dict[str, tuple[str, ...]] = {
    "hvac": _HVAC_TERMS,
    "heating and cooling": _HVAC_TERMS,
    "air conditioning": _HVAC_TERMS,
    "service": _SERVICE_TERMS,
    "services": _SERVICE_TERMS,
    "home service": _SERVICE_TERMS,
    "home services": _SERVICE_TERMS,
    "local service": _SERVICE_TERMS,
    "local services": _SERVICE_TERMS,
    "repair": _SERVICE_TERMS,
    "repairs": _SERVICE_TERMS,
    "install": _SERVICE_TERMS,
    "installation": _SERVICE_TERMS,
    "installations": _SERVICE_TERMS,
    "maintenance": _SERVICE_TERMS,
    "contractor": _SERVICE_TERMS,
    "contractors": _SERVICE_TERMS,
    "auto": _AUTOMOTIVE_TERMS,
    "automotive": _AUTOMOTIVE_TERMS,
    "car": _AUTOMOTIVE_TERMS,
    "cars": _AUTOMOTIVE_TERMS,
    "vehicle": _AUTOMOTIVE_TERMS,
    "vehicles": _AUTOMOTIVE_TERMS,
    "truck": _AUTOMOTIVE_TERMS,
    "trucks": _AUTOMOTIVE_TERMS,
    "suv": _AUTOMOTIVE_TERMS,
    "suvs": _AUTOMOTIVE_TERMS,
    "dealer": _AUTOMOTIVE_TERMS,
    "dealership": _AUTOMOTIVE_TERMS,
    "food": _FOOD_TERMS,
    "restaurant": _FOOD_TERMS,
    "restaurants": _FOOD_TERMS,
    "pizza": _FOOD_TERMS,
    "delivery": _FOOD_TERMS,
    "coffee": _FOOD_TERMS,
    "beverage": _FOOD_TERMS,
    "beverages": _FOOD_TERMS,
    "health": _HEALTH_TERMS,
    "medical": _HEALTH_TERMS,
    "doctor": _HEALTH_TERMS,
    "doctors": _HEALTH_TERMS,
    "clinic": _HEALTH_TERMS,
    "dental": _HEALTH_TERMS,
    "dentist": _HEALTH_TERMS,
    "dentists": _HEALTH_TERMS,
    "pharmacy": _HEALTH_TERMS,
    "fitness": _HEALTH_TERMS,
    "finance": _FINANCE_TERMS,
    "financial": _FINANCE_TERMS,
    "bank": _FINANCE_TERMS,
    "banking": _FINANCE_TERMS,
    "loan": _FINANCE_TERMS,
    "loans": _FINANCE_TERMS,
    "credit": _FINANCE_TERMS,
    "mortgage": _FINANCE_TERMS,
    "insurance": _FINANCE_TERMS,
    "retail": _RETAIL_TERMS,
    "ecommerce": _RETAIL_TERMS,
    "e-commerce": _RETAIL_TERMS,
    "shop": _RETAIL_TERMS,
    "shopping": _RETAIL_TERMS,
    "store": _RETAIL_TERMS,
    "stores": _RETAIL_TERMS,
    "travel": _TRAVEL_TERMS,
    "hotel": _TRAVEL_TERMS,
    "hotels": _TRAVEL_TERMS,
    "flight": _TRAVEL_TERMS,
    "flights": _TRAVEL_TERMS,
    "vacation": _TRAVEL_TERMS,
    "education": _EDUCATION_TERMS,
    "school": _EDUCATION_TERMS,
    "schools": _EDUCATION_TERMS,
    "college": _EDUCATION_TERMS,
    "university": _EDUCATION_TERMS,
    "training": _EDUCATION_TERMS,
    "real estate": _REAL_ESTATE_TERMS,
    "home": _REAL_ESTATE_TERMS,
    "homes": _REAL_ESTATE_TERMS,
    "house": _REAL_ESTATE_TERMS,
    "houses": _REAL_ESTATE_TERMS,
    "apartment": _REAL_ESTATE_TERMS,
    "apartments": _REAL_ESTATE_TERMS,
    "rent": _REAL_ESTATE_TERMS,
    "realtor": _REAL_ESTATE_TERMS,
    "streaming": _ENTERTAINMENT_TERMS,
    "entertainment": _ENTERTAINMENT_TERMS,
    "movie": _ENTERTAINMENT_TERMS,
    "movies": _ENTERTAINMENT_TERMS,
    "show": _ENTERTAINMENT_TERMS,
    "shows": _ENTERTAINMENT_TERMS,
    "app": _APPS_GAMES_TERMS,
    "apps": _APPS_GAMES_TERMS,
    "game": _APPS_GAMES_TERMS,
    "games": _APPS_GAMES_TERMS,
    "mobile": _APPS_GAMES_TERMS,
}


def expand_query_terms(query: str | None) -> list[str]:
    """Expand common business shorthand into terms present in stored ad text."""
    normalized = " ".join((query or "").strip().split())
    if not normalized:
        return []

    terms = [normalized]
    lowered = normalized.lower()
    tokens = set(re.findall(r"[a-z0-9]+", lowered))

    for trigger, expansions in _ALIASES.items():
        if trigger in tokens or trigger in lowered:
            terms.extend(expansions)

    seen: set[str] = set()
    deduped: list[str] = []
    for term in terms:
        key = term.casefold()
        if key not in seen:
            seen.add(key)
            deduped.append(term)
    return deduped


def has_alias_expansion(query: str | None) -> bool:
    terms = expand_query_terms(query)
    return len(terms) > 1


def build_loose_like_clause(
    query: str | None,
    *,
    columns: Iterable[str] = DEFAULT_AD_SEARCH_COLUMNS,
) -> tuple[str | None, list[str]]:
    terms = expand_query_terms(query)
    cols = tuple(columns)
    if not terms or not cols:
        return None, []

    term_clauses: list[str] = []
    params: list[str] = []
    for term in terms:
        term_clauses.append("(" + " OR ".join(f"{column} LIKE ?" for column in cols) + ")")
        params.extend(f"%{term}%" for _ in cols)

    return "(" + " OR ".join(term_clauses) + ")", params
