"""Shared category -> key-builder mapping used by migrate_storage.py,
user_export.py, and user_import.py, so the list of per-user categories and
their storage keys has one source of truth across all three scripts."""
from __future__ import annotations

from pathlib import Path

from handler import (
    _eyepieces_key_for_user,
    _finding_paths_key_for_user,
    _lists_key_for_user,
    _observations_key_for_user,
    _telescopes_key_for_user,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

# Key builders imported from handler.py, the single source of truth for the
# current (users/{username}/{category}.json) key format.
CATEGORY_KEY_FNS = {
    "observations": _observations_key_for_user,
    "finding-paths": _finding_paths_key_for_user,
    "telescopes": _telescopes_key_for_user,
    "eyepieces": _eyepieces_key_for_user,
    "lists": _lists_key_for_user,
}
