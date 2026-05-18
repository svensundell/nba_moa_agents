"""OpenRouter pricing table for the MoA model lineup.

Prices are expressed in **USD per 1 million tokens** to match the format
OpenRouter publishes on its model cards. They are intentionally hard-coded
rather than fetched at runtime so cost estimates stay deterministic in
offline tests and CI, and so the eval dashboard never blocks on a pricing
API. When OpenRouter adjusts a model price, update the table here.

Unknown models fall back to ``DEFAULT_PRICE`` (a conservative mid-range
estimate) and are tagged ``estimated=True`` in :class:`ModelPrice` so the
UI can flag the value as approximate.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPrice:
    """Price for a single OpenRouter model, in USD per 1M tokens."""

    prompt_per_1m_usd: float
    completion_per_1m_usd: float
    estimated: bool = False


# Snapshot of OpenRouter prices for the models declared in
# ``app.moa.llm.MODEL_REGISTRY``. The keys are the *provider* model ids
# (the strings actually sent to OpenRouter), not the logical role names.
PRICES: dict[str, ModelPrice] = {
    "deepseek/deepseek-chat-v3.1": ModelPrice(0.27, 1.10),
    "deepseek/deepseek-v4-pro": ModelPrice(0.55, 2.19, estimated=True),
    "google/gemini-2.5-flash": ModelPrice(0.075, 0.30),
    "qwen/qwen3.6-35b-a3b": ModelPrice(0.20, 0.60, estimated=True),
    "mistralai/mistral-small-24b-instruct-2501": ModelPrice(0.20, 0.60),
}

# Default for models not in the table — conservative middle-of-the-road.
DEFAULT_PRICE = ModelPrice(0.30, 1.00, estimated=True)


def price_for_model(model_id: str | None) -> ModelPrice:
    """Return the :class:`ModelPrice` for an OpenRouter ``model_id``.

    Falls back to :data:`DEFAULT_PRICE` (with ``estimated=True``) when the
    id is not in the table.
    """
    if not model_id:
        return DEFAULT_PRICE
    return PRICES.get(model_id, DEFAULT_PRICE)


def cost_usd(
    *,
    input_tokens: int,
    output_tokens: int,
    model_id: str | None,
) -> float:
    """Compute USD cost from prompt + completion token counts.

    Tokens are clamped to ``0`` to defend against bogus negative values
    returned by the SDK when a streamed message ends without a usage
    payload.
    """
    price = price_for_model(model_id)
    in_tok = max(0, int(input_tokens))
    out_tok = max(0, int(output_tokens))
    return (
        in_tok * price.prompt_per_1m_usd / 1_000_000.0
        + out_tok * price.completion_per_1m_usd / 1_000_000.0
    )
