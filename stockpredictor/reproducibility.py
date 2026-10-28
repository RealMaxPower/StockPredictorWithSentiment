"""Identities for the actual monthly inputs and installed implementation."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd


def data_fingerprint(monthly: pd.Series) -> str:
    digest = hashlib.sha256()
    digest.update("\n".join(timestamp.isoformat() for timestamp in monthly.index).encode())
    digest.update(monthly.to_numpy(dtype="<f8").tobytes())
    return digest.hexdigest()


def code_version() -> str:
    """Hash package source so uncommitted changes and installed wheels are identified."""
    digest = hashlib.sha256()
    for source in sorted(Path(__file__).parent.glob("*.py")):
        digest.update(source.name.encode())
        digest.update(source.read_bytes())
    return "sha256:" + digest.hexdigest()
