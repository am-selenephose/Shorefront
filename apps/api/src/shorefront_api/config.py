"""Canonical settings with a bounded compatibility window for pre-rename installs."""
from __future__ import annotations

import os


def setting(suffix: str, default: str | None = None) -> str | None:
    """Presence wins: an explicitly empty new setting never revives an old value."""
    canonical = f"SHOREFRONT_{suffix}"
    if canonical in os.environ:
        return os.environ[canonical]
    return os.environ.get(f"PORTFLOW_{suffix}", default)
