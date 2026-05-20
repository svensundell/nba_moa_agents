"""EditorAgent — final aggregator that produces the user-facing briefing.

Receives:
- the original ``mode`` and ``query``
- the layer-1 proposals (raw drafts)
- the layer-2 refinements (analyst fact-sheet + narrative)

Outputs:
- A polished markdown brief if mode=="brief"
- A focused answer if mode=="query"
- A briefing-style answer if mode=="compare" (single-LLM baseline runs in parallel)
"""

from __future__ import annotations

from app.eval import current_tracker
from app.moa.agents.base import call_llm, event
from app.moa.citations import format_citation_index, merge_run_citations
from app.moa.llm import AGENT_MODELS, model_id
from app.moa.state import MoAState

BRIEF_SYSTEM = """You are the editor-in-chief of a daily NBA briefing called
"Last Night in the NBA". Compose the briefing in markdown using EXACTLY this
structure:

```
# Last Night in the NBA — {date}

## Quick Hits
- (3 bullets max, one-line each)

## Box Score Recap
(Two short paragraphs, max ~120 words.)

## Standout Statlines
- (2-4 bullets. Each bullet must include an EXACT statline lifted from the
  stats draft, e.g. `Austin Reaves (Lakers): 8 pts on 3-of-16 FG, 4 TO`.
  Mix positive and negative standouts when both are available.)

## Trades, Rumors & News
(Bullets covering the verified news from the fact sheet.)

## Injuries Watch
(Bullets, only verified statuses.)

## Storyline of the Night
(Two paragraphs, lifted from the narrative draft but tightened.)

## Fan Pulse
(One short paragraph from the social draft.)
```

Rules:
- Stay strictly within the facts from the analyst sheet and the proposers.
- For Standout Statlines, only use lines that already appear in the stats draft.
  If the stats draft has no exact statline, write "No notable items today.".
- Never invent stats, scores, or quotes.
- If a section has no data, write "No notable items today." instead of skipping.
- No emojis, no clickbait headlines.
- When stating a fact grounded in a reporter draft, add an inline citation [n]
  using the source index below (one number per distinct source).
- Do not invent citation numbers — only use ids from the provided index.
"""


QUERY_SYSTEM = """You are an expert NBA analyst answering a specific user question.
You have access to:
- A consolidated fact sheet from a fact-checker.
- A storyline angle from a narrative writer.
- The original raw drafts from five specialised reporters.

Answer the question concisely (2-4 paragraphs) in markdown, citing concrete
data points. When evidence is thin, say so explicitly rather than guessing.
"""


def _language_instruction(language: str) -> str:
    if language == "fr":
        return "Write the final output in French.\nKeep section headings and prose in French."
    return "Write the final output in English."


def _drafts_block(state: MoAState) -> str:
    return "\n\n".join(
        f"### {p.agent} (model: {p.model})\n{p.summary}" for p in state.get("proposals", [])
    )


def _refinements_block(state: MoAState) -> str:
    return "\n\n".join(
        f"### {r.agent} (model: {r.model})\n{r.content}" for r in state.get("refinements", [])
    )


async def editor_agent(state: MoAState) -> dict:
    mode = state.get("mode", "brief")
    language = state.get("language", "en")
    date = state.get("date", "")
    query = state.get("query", "")

    drafts = _drafts_block(state)
    refinements = _refinements_block(state)
    tracker = current_tracker()
    citations = merge_run_citations(tracker, state.get("proposals", []))
    index_block = format_citation_index(citations)

    if mode == "query":
        system = f"{QUERY_SYSTEM}\n\n{_language_instruction(language)}"
        user = (
            f"User question: {query}\n\n"
            f"Refinements:\n{refinements}\n\n"
            f"Raw drafts:\n{drafts}\n\n"
            f"Source index (use [n] inline when citing facts):\n{index_block}\n\n"
            "Write the answer."
        )
    else:
        system = f"{BRIEF_SYSTEM.replace('{date}', date)}\n\n{_language_instruction(language)}"
        user = (
            f"Refinements:\n{refinements}\n\n"
            f"Raw drafts:\n{drafts}\n\n"
            f"Source index (use [n] inline when citing facts):\n{index_block}\n\n"
            "Write the full briefing now."
        )

    content = await call_llm("editor", system=system, user=user)
    model = model_id(AGENT_MODELS.get("editor", "balanced"))
    return {
        "final_brief": content,
        "events": [event("editor", "aggregator", "done", content="brief ready", model=model)],
    }


# ─── Single-LLM baseline (for the comparison mode) ───────────────────────────


BASELINE_SYSTEM = """You are an NBA expert. Answer the user with the best
information you have, in the same markdown style as a daily briefing if it's
a generic 'tell me about today' request, otherwise as a focused answer.
Do not pretend to have data you don't have.
"""


async def baseline_agent(state: MoAState) -> dict:
    """Single-shot single-model answer used by the 'compare' mode."""
    if state.get("mode") != "compare":
        return {"single_llm_answer": ""}
    language = state.get("language", "en")
    query = state.get("query") or "Give me a daily NBA briefing."
    system = f"{BASELINE_SYSTEM}\n\n{_language_instruction(language)}"
    answer = await call_llm("single_llm_baseline", system=system, user=query)
    model = model_id(AGENT_MODELS.get("single_llm_baseline", "balanced"))
    return {
        "single_llm_answer": answer,
        "events": [event("baseline", "system", "done", content="baseline ready", model=model)],
    }
