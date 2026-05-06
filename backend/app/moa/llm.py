"""LLM model registry + OpenRouter factory used by every MoA agent."""

from __future__ import annotations

from dataclasses import dataclass

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from app.core.config import get_settings


@dataclass(frozen=True)
class ModelSpec:
    name: str
    model_id: str
    temperature: float = 0.4
    max_tokens: int = 2048
    description: str = ""


# Logical roles kept for MoA diversity, all routed through OpenRouter.
MODEL_REGISTRY: dict[str, ModelSpec] = {
    "balanced": ModelSpec(
        name="balanced",
        model_id="deepseek/deepseek-chat-v3.1",
        temperature=0.4,
        description="Balanced synthesis model for editor/refiner roles.",
    ),
    "fast": ModelSpec(
        name="fast",
        model_id="google/gemini-2.5-flash",
        temperature=0.3,
        description="Fast proposer model with strong quality/latency ratio.",
    ),
    "reasoner": ModelSpec(
        name="reasoner",
        model_id="qwen/qwen3.6-35b-a3b",
        temperature=0.5,
        description="Mid-tier reasoner for analysis and multi-step synthesis.",
    ),
    "synthesis": ModelSpec(
        name="synthesis",
        model_id="deepseek/deepseek-chat-v3.1",
        temperature=0.4,
        description="High-quality deepseek synthesis and reasoning fallback.",
    ),
    "budget": ModelSpec(
        name="budget",
        model_id="mistralai/mistral-small-24b-instruct-2501",
        temperature=0.6,
        description="Cheap and fast social/sentiment fallback model.",
    ),
    "open_query": ModelSpec(
        name="open_query",
        model_id="deepseek/deepseek-v4-pro",
        temperature=0.2,
        description="High-accuracy tool-using model for NBA Copilot.",
    ),
}

DEFAULT_MODEL = "balanced"


def get_model(name: str, *, temperature: float | None = None) -> BaseChatModel:
    """Instantiate a chat model for a logical model name via OpenRouter."""
    settings = get_settings()
    if not settings.has_openrouter:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Add it to your .env file."
        )
    spec = MODEL_REGISTRY.get(name) or MODEL_REGISTRY[DEFAULT_MODEL]
    temp = temperature if temperature is not None else spec.temperature
    return ChatOpenAI(
        model=spec.model_id,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        temperature=temp,
        max_tokens=spec.max_tokens,
    )


def model_id(name: str) -> str:
    """Resolve a logical model name to the OpenRouter model id."""
    spec = MODEL_REGISTRY.get(name) or MODEL_REGISTRY[DEFAULT_MODEL]
    return spec.model_id


# ─── Per-agent model assignments (the MoA "lineup") ──────────────────────────
#
# This is the single source of truth for "who uses what". Tweaking this dict
# changes the entire MoA composition without touching agent code.

AGENT_MODELS: dict[str, str] = {
    # Layer 1 — Proposers
    "scores": "fast",
    "news": "fast",
    "stats": "reasoner",
    "injuries": "fast",
    "social": "budget",
    # Layer 2 — Refiners
    "analyst": "reasoner",
    "narrative": "synthesis",
    # Layer 3 — Aggregator
    "editor": "balanced",
    # Comparison baseline
    "single_llm_baseline": "balanced",
    # NBA Copilot (query mode)
    "nba_copilot": "open_query",
}
