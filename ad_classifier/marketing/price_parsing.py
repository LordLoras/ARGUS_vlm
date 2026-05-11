from __future__ import annotations

from ad_classifier.marketing._utils import compact_key as _compact_key
from ad_classifier.marketing._utils import currency_symbol as _currency_symbol
from ad_classifier.marketing._utils import format_price as _format_price
from ad_classifier.models.marketing import PriceEntity


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
