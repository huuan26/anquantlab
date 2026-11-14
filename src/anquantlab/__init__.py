"""AnQuantLab: Interactive Quantitative Alpha & Falsification Workbench."""

from __future__ import annotations

from .config import Settings, apply_thread_limits, load_settings

apply_thread_limits()

__version__ = "0.1.0a1"

__all__ = [
    "Settings",
    "__version__",
    "apply_thread_limits",
    "load_settings",
]
