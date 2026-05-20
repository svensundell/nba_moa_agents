"""Brief memory for NBA Copilot — chunk, embed, and retrieve past Daily Briefs."""

from app.memory.service import MemoryService, configure_memory, get_memory_service

__all__ = ["MemoryService", "configure_memory", "get_memory_service"]
