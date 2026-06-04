"""Shared helpers for the SMB Order & AR Risk Monitor."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"


def format_currency(value: float) -> str:
    """Format a numeric amount as a compact RMB-style display string."""
    if value is None:
        value = 0
    return f"¥{float(value):,.0f}"


def normalize_code_series(series):
    """Normalize service station and id-like columns to stripped strings."""
    return series.astype(str).str.strip()

