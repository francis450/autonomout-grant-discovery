"""Org profile service layer — module 01.

Full spec: docs/modules/01-org-profile.md

Phase 1-3 YAML loader is fully implemented below (§7, §8 — purely mechanical,
no judgment calls). Phase 4 DB-backed versioned store is stubbed; swap the
backend behind load_org_profile() without changing callers (§10).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from app.org_profile.schema import OrgProfile

DEFAULT_PROFILE_PATH = Path("config/org_profile.yaml")


def _canonical_bytes(raw: dict) -> bytes:
    """Sorted-key JSON re-serialization so incidental YAML formatting/comment
    changes don't spuriously bump the version, but any value change does.
    See §8.
    """
    return json.dumps(raw, sort_keys=True, default=str).encode("utf-8")


def _validate(profile_data: dict) -> None:
    """§7.4 validation rules — fail loudly, never silently default."""
    award = profile_data.get("award_range_usd") or {}
    if award and award.get("ideal_min") is not None and award.get("ideal_max") is not None:
        if award["ideal_min"] > award["ideal_max"]:
            raise ValueError("org_profile: award_range_usd.ideal_min > ideal_max")
        if award.get("hard_max") is not None and award["ideal_max"] > award["hard_max"]:
            raise ValueError("org_profile: award_range_usd.ideal_max > hard_max")
    for pillar, cfg in (profile_data.get("pillars") or {}).items():
        weight = (cfg or {}).get("weight")
        if weight is not None and not (0.0 <= weight <= 1.0):
            raise ValueError(f"org_profile: pillar '{pillar}' weight {weight} outside [0, 1]")
    if not profile_data.get("legal_entities"):
        raise ValueError("org_profile: legal_entities must not be empty")


def load_org_profile(path: Path = DEFAULT_PROFILE_PATH) -> OrgProfile:
    """Phase 1-3 loader: reads YAML, validates, stamps a content-hash
    profile_version. Raises on missing/invalid fields rather than
    defaulting — this module is on the critical path for every scoring run.
    See §7.1-§7.4, §11.
    """
    if not path.exists():
        raise FileNotFoundError(f"org profile not found at {path}")

    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    _validate(raw)

    version = hashlib.sha256(_canonical_bytes(raw)).hexdigest()[:12]
    raw["profile_version"] = version
    return OrgProfile.model_validate(raw)


def load_org_profile_db() -> OrgProfile:
    """Phase 4: load the `is_current` row from org_profile_versions. See §6."""
    raise NotImplementedError("Phase 4 — see docs/modules/01-org-profile.md §6, §10")
