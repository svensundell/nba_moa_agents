"""CLI demo runner — invoke the full MoA pipeline and print the result.

Usage:

    python -m scripts.demo brief
    python -m scripts.demo query "How is Luka playing this season?"
    python -m scripts.demo compare "What should the Lakers do at the deadline?"

Useful for screen-recording the pipeline without spinning up the frontend.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime

from app.api.runner import run_full
from app.core.credentials import use_openrouter_api_key
from app.core.logging import configure_logging

HELP = """\
Usage:
  python -m scripts.demo brief
  python -m scripts.demo query "<your NBA question>"
  python -m scripts.demo compare "<your NBA question>"
"""


async def _main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] in {"-h", "--help"}:
        print(HELP)
        return 0

    mode = sys.argv[1]
    if mode not in {"brief", "query", "compare"}:
        print(HELP)
        return 1
    query = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
    if mode in {"query", "compare"} and not query:
        print("error: query/compare modes require a question.")
        print(HELP)
        return 1

    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        print("error: export OPENROUTER_API_KEY in your shell (BYOK — same key as the web UI).")
        print(HELP)
        return 1

    configure_logging()
    started = datetime.now()
    print(f"\n=== Running MoA pipeline (mode={mode}) ===\n")
    with use_openrouter_api_key(api_key):
        result = await run_full(mode, query=query)  # type: ignore[arg-type]
    print(f"\n--- Done in {(datetime.now() - started).total_seconds():.1f}s ---\n")

    print("# Final brief\n")
    print(result.final_brief or "(empty)")

    if mode == "compare":
        print("\n\n# NBA Copilot (compare baseline)\n")
        print(result.single_llm_answer or "(empty)")

    print("\n\n# Per-agent proposals")
    for p in result.proposals:
        print(f"\n## {p.agent} ({p.model})")
        print(p.summary)

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
