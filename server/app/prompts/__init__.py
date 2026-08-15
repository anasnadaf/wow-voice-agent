"""Prompt package: sections, knowledge base and assembly for the WOW voice agent."""

from app.prompts.assemble import (
    full_system_prompt,
    language_directive,
    speech_tags_required,
    system_prompt_for_turn,
)
from app.prompts.knowledge import AMENITIES, CONNECTIVITY, PROJECT, knowledge_block

__all__ = [
    "AMENITIES",
    "CONNECTIVITY",
    "PROJECT",
    "full_system_prompt",
    "knowledge_block",
    "language_directive",
    "speech_tags_required",
    "system_prompt_for_turn",
]
