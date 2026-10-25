"""Model prices, for `cost_usd` on llm_requests (docs/llm-gateway.md).

Prices come from llm_prices.json (LLM_PRICES_FILE), with LLM_PRICES (JSON)
overriding single entries. Keys are matched like llm_limits.json:
'provider/model' first, then 'provider/*'. Fields, all optional, USD:
  input_per_million, output_per_million  per 1M tokens
  cached_input_per_million               cached prompt tokens (default: input)
  per_image                              per generated image
A model without a price records cost_usd = NULL, never a guess.
"""

import json
from decimal import Decimal
from functools import cache
from pathlib import Path

from app.ai.limits import BACKEND_DIR
from app.core.config import Settings, get_settings
from app.core.logging import logger

MILLION = Decimal(1_000_000)


@cache
def _file_prices(name: str) -> dict[str, dict]:
    if not name or name.lower() == "off":
        return {}
    path = Path(name) if Path(name).is_absolute() else BACKEND_DIR / name
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.warning("LLM price file %s not found; costs won't be recorded", path)
        return {}
    except ValueError as exc:
        logger.warning("LLM price file %s is not valid JSON (%s)", path, exc)
        return {}
    return {k: v for k, v in raw.items() if not k.startswith("_") and isinstance(v, dict)}


def price_for(provider: str, model: str, settings: Settings | None = None) -> dict | None:
    settings = settings or get_settings()
    prices = {**_file_prices(settings.llm_prices_file), **settings.llm_prices}
    return prices.get(f"{provider}/{model}") or prices.get(f"{provider}/*")


def _dec(value: object) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def cost_usd(
    provider: str,
    model: str,
    *,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cached_input_tokens: int | None = None,
    images: int | None = None,
    settings: Settings | None = None,
) -> Decimal | None:
    """What one request cost, or None when the model has no price for what it
    used (or reported no usage)."""
    price = price_for(provider, model, settings)
    if not price:
        return None
    total = Decimal(0)
    used = False
    if images:
        per_image = _dec(price.get("per_image"))
        if per_image is None:
            return None
        total += per_image * images
        used = True
    if input_tokens is not None or output_tokens is not None:
        rate_in = _dec(price.get("input_per_million"))
        rate_out = _dec(price.get("output_per_million"))
        if (input_tokens and rate_in is None) or (output_tokens and rate_out is None):
            return None
        cached = min(cached_input_tokens or 0, input_tokens or 0)
        rate_cached = _dec(price.get("cached_input_per_million"))
        if rate_cached is None:
            rate_cached = rate_in
        total += (Decimal((input_tokens or 0) - cached) * (rate_in or 0)) / MILLION
        total += (Decimal(cached) * (rate_cached or 0)) / MILLION
        total += (Decimal(output_tokens or 0) * (rate_out or 0)) / MILLION
        used = True
    return total.quantize(Decimal("0.000001")) if used else None
