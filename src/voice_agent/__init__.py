"""Compatibility package for legacy voice agent import paths."""

from importlib import import_module

__all__ = ["voiceflow_rag"]


def __getattr__(name: str):
    if name == "voiceflow_rag":
        return import_module(f"{__name__}.voiceflow_rag")
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
