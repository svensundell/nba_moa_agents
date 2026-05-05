"""AnalystAgent — cross-references the layer-1 proposals for accuracy.

The analyst's job is to consolidate facts and call out contradictions. Its
output goes into the editor's context as a high-confidence "what we know"
section.
"""

from __future__ import annotations

from app.moa.agents.base import call_llm, event
from app.moa.llm import AGENT_MODELS, model_id
from app.moa.state import AgentRefinement, MoAState

SYSTEM = """You are the senior fact-checker of an NBA editorial team.
You receive five drafts produced by separate junior reporters covering
scores, news, stats, injuries and social signal.

Your job:
1. Extract the *consolidated* set of verified facts (max 8 bullets).
2. Flag any apparent contradiction between drafts.
3. Note clear gaps where a draft was empty so the editor knows.

Be terse. No filler. Markdown bullets only.
"""


async def analyst_agent(state: MoAState) -> dict:
    proposals = state.get("proposals", [])
    if not proposals:
        return {
            "refinements": [],
            "events": [event("analyst", "refiner", "done", content="no proposals")],
        }

    drafts = "\n\n".join(f"### {p.agent} (model: {p.model})\n{p.summary}" for p in proposals)
    user = f"Drafts:\n\n{drafts}\n\nProduce the consolidated fact sheet."
    content = await call_llm("analyst", system=SYSTEM, user=user)

    ref = AgentRefinement(
        agent="analyst",
        model=model_id(AGENT_MODELS.get("analyst", "llama-versatile")),
        content=content,
    )
    return {
        "refinements": [ref],
        "events": [event("analyst", "refiner", "done", content=content[:160], model=ref.model)],
    }
