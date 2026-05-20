"""Split Daily Brief markdown into section-sized chunks for retrieval."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class BriefChunkDraft:
    section: str
    content: str


_SECTION_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)
_TITLE_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


def extract_brief_title(markdown: str) -> str:
    match = _TITLE_RE.search(markdown.strip())
    if match:
        return match.group(1).strip()
    first = markdown.strip().splitlines()[0] if markdown.strip() else ""
    return first.lstrip("# ").strip()[:200]


def chunk_brief_markdown(markdown: str, *, max_chunk_chars: int = 1200) -> list[BriefChunkDraft]:
    """Split a brief into sections; oversized sections are split on paragraphs."""
    text = markdown.strip()
    if not text:
        return []

    parts = _SECTION_RE.split(text)
    chunks: list[BriefChunkDraft] = []

    if len(parts) == 1:
        return _split_oversized("Overview", text, max_chunk_chars=max_chunk_chars)

    preamble = parts[0].strip()
    if preamble:
        chunks.extend(_split_oversized("Overview", preamble, max_chunk_chars=max_chunk_chars))

    for i in range(1, len(parts), 2):
        section = parts[i].strip() or "Section"
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        if not body:
            continue
        block = f"## {section}\n\n{body}".strip()
        chunks.extend(_split_oversized(section, block, max_chunk_chars=max_chunk_chars))

    return chunks


def _split_oversized(
    section: str,
    content: str,
    *,
    max_chunk_chars: int,
) -> list[BriefChunkDraft]:
    if len(content) <= max_chunk_chars:
        return [BriefChunkDraft(section=section, content=content)]

    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    if not paragraphs:
        return [BriefChunkDraft(section=section, content=content[:max_chunk_chars])]

    out: list[BriefChunkDraft] = []
    buf: list[str] = []
    buf_len = 0
    part = 1

    def flush() -> None:
        nonlocal part, buf, buf_len
        if not buf:
            return
        name = section if part == 1 and len(out) == 0 else f"{section} ({part})"
        out.append(BriefChunkDraft(section=name, content="\n\n".join(buf)))
        part += 1
        buf = []
        buf_len = 0

    for para in paragraphs:
        extra = len(para) + (2 if buf else 0)
        if buf and buf_len + extra > max_chunk_chars:
            flush()
        buf.append(para)
        buf_len += extra
    flush()
    return out or [BriefChunkDraft(section=section, content=content[:max_chunk_chars])]
