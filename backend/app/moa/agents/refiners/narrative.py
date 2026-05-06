"""NarrativeAgent — finds the storylines threading through the day.

Where the analyst is dry and factual, the narrative agent looks for the
*through-line*: the human-interest hook that makes a brief feel curated
rather than auto-generated.
"""

from __future__ import annotations

from app.moa.agents.base import call_llm, event
from app.moa.llm import AGENT_MODELS, model_id
from app.moa.state import AgentRefinement, MoAState

SYSTEM = """You are an NBA storyteller — the kind of writer that turns box scores
into narrative arcs.

Given five raw drafts (scores, news, stats, injuries, social), identify
ONE OR TWO storylines worth highlighting in tonight's brief. For each, give:

- A punchy 5-8 word title.
- A short paragraph (3-5 sentences) developing the angle, weaving in
  details from multiple drafts when possible.

Avoid clichés ("the underdog story", "the GOAT debate") unless genuinely
warranted. No emojis.
"""


async def narrative_agent(state: MoAState) -> dict:
    proposals = state.get("proposals", [])
    if not proposals:
        return {"refinements": [], "events": [event("narrative", "refiner", "done", content="no proposals")]}

    drafts = "\n\n".join(f"### {p.agent}\n{p.summary}" for p in proposals)
    user = f"Drafts:\n\n{drafts}\n\nFind the storyline(s)."
    content = await call_llm("narrative", system=SYSTEM, user=user)

    ref = AgentRefinement(
        agent="narrative",
        model=model_id(AGENT_MODELS.get("narrative", "reasoner")),
        content=content,
    )
    return {
        "refinements": [ref],
        "events": [event("narrative", "refiner", "done", content=content[:160], model=ref.model)],
    }
