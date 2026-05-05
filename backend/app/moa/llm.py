"""Groq model registry — the heart of MoA's *real* model diversity.

Each agent in the graph is mapped to a specific Groq model so that the
ensemble truly mixes architectures (Llama, Qwen, DeepSeek, Mixtral, Gemma).
That's what distinguishes a real MoA from "the same LLM with 8 prompts".
"""

from __future__ import annotations

from dataclasses import dataclass

from langchain_groq import ChatGroq

from app.core.config import get_settings


@dataclass(frozen=True)
class ModelSpec:
    name: str
    groq_id: str
    temperature: float = 0.4
    max_tokens: int = 2048
    description: str = ""


# Curated lineup as of 2026 — keep this list trimmed to currently-served Groq models.
# If a model gets deprecated, the registry will fall back to `DEFAULT_MODEL`.
MODEL_REGISTRY: dict[str, ModelSpec] = {
    "llama-versatile": ModelSpec(
        name="llama-versatile",
        groq_id="llama-3.3-70b-versatile",
        temperature=0.4,
        description="Strong all-rounder, used by the editor.",
    ),
    "llama-fast": ModelSpec(
        name="llama-fast",
        # groq_id="llama-3.1-8b-instant",
        groq_id="llama-3.3-70b-versatile",
        temperature=0.3,
        description="Cheap & fast, perfect for short proposers.",
    ),
    "qwen-reasoner": ModelSpec(
        name="qwen-reasoner",
        groq_id="llama-3.3-70b-versatile",
        temperature=0.5,
        description="Reasoning-tuned fallback for narrative & analysis.",
    ),
    "deepseek-reasoner": ModelSpec(
        name="deepseek-reasoner",
        groq_id="llama-3.3-70b-versatile",
        temperature=0.4,
        description="High-reasoning fallback on currently supported IDs.",
    ),
    "gemma": ModelSpec(
        name="gemma",
        # groq_id="llama-3.1-8b-instant",
        groq_id="llama-3.3-70b-versatile",
        temperature=0.6,
        description="Fast social/sentiment model on currently supported Groq IDs.",
    ),
}

DEFAULT_MODEL = "llama-versatile"


def get_model(name: str, *, temperature: float | None = None) -> ChatGroq:
    """Instantiate a ChatGroq for a logical model name.

    The function is intentionally cheap — ChatGroq is just a thin wrapper
    around the SDK, so we recreate them per call to allow per-agent tweaks.
    """
    settings = get_settings()
    if not settings.has_groq:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Get one for free at https://console.groq.com "
            "and add it to your .env file."
        )

    spec = MODEL_REGISTRY.get(name) or MODEL_REGISTRY[DEFAULT_MODEL]
    return ChatGroq(
        model=spec.groq_id,
        api_key=settings.groq_api_key,
        temperature=temperature if temperature is not None else spec.temperature,
        max_tokens=spec.max_tokens,
    )


def model_id(name: str) -> str:
    """Resolve a logical model name to its Groq id (for display/logging)."""
    spec = MODEL_REGISTRY.get(name) or MODEL_REGISTRY[DEFAULT_MODEL]
    return spec.groq_id


# ─── Per-agent model assignments (the MoA "lineup") ──────────────────────────
#
# This is the single source of truth for "who uses what". Tweaking this dict
# changes the entire MoA composition without touching agent code.

AGENT_MODELS: dict[str, str] = {
    # Layer 1 — Proposers
    "scores": "llama-fast",
    "news": "qwen-reasoner",
    "stats": "deepseek-reasoner",
    "injuries": "llama-fast",
    "social": "gemma",
    # Layer 2 — Refiners
    "analyst": "llama-versatile",
    "narrative": "qwen-reasoner",
    # Layer 3 — Aggregator
    "editor": "llama-versatile",
    # Comparison baseline
    "single_llm_baseline": "llama-versatile",
}
