"""Backward-compatible shim for the experimental Voiceflow client."""

from src.experimental.voice_agent.voiceflow_rag import VoiceflowRAG, get_voiceflow_client

__all__ = ["VoiceflowRAG", "get_voiceflow_client"]
