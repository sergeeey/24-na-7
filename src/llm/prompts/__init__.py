"""Единый интерфейс для управления промптами."""
from typing import Dict, Any, Optional
from src.llm.prompts.manager import PromptManager, get_prompt

__all__ = ["PromptManager", "get_prompt"]
