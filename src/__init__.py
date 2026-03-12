"""Reflexio 24/7 — умный диктофон и дневной анализатор."""

from importlib import import_module

__version__ = "0.1.0"

__all__ = ["voice_agent"]


def __getattr__(name: str):
    if name == "voice_agent":
        return import_module(f"{__name__}.voice_agent")
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

