from __future__ import annotations

from ad_classifier.models.marketing import PriceEntity
from ad_classifier.marketing.product_utils import _compact_key


def _price_key(price: PriceEntity) -> str:
    if price.amount is not None:
        return f"{_currency_symbol(price.currency)}:{price.amount:.2f}"
    return _compact_key(price.text)


def _normalize_price_entity(price: PriceEntity) -> PriceEntity:
    if price.amount is None:
        return price
    currency = _currency_symbol(price.currency)
    text = _format_price(currency, price.amount)
    return price.model_copy(update={"currency": currency, "text": text})


def _currency_symbol(currency: str | None) -> str:
    normalized = (currency or "$").strip().upper()
    if normalized in {"USD", "US$", "$"}:
        return "$"
    return currency or "$"


def _format_price(currency: str | None, amount: float) -> str:
    amount_text = (
        f"{int(amount):,}"
        if float(amount).is_integer()
        else f"{amount:,.2f}".rstrip("0").rstrip(".")
    )
    return f"{_currency_symbol(currency)}{amount_text}"
