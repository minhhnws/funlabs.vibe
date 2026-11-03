"""Versioned local JSON preset persistence."""
from __future__ import annotations

import json
from pathlib import Path

from .state import AudioState, state_from_dict, state_to_dict, validate_state

PRESET_VERSION = 1


class PresetVersionError(ValueError):
    pass


def save_preset(path: str | Path, state: AudioState) -> None:
    payload = {"schema_version": PRESET_VERSION, "state": state_to_dict(validate_state(state))}
    Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_preset(path: str | Path) -> AudioState:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != PRESET_VERSION:
        raise PresetVersionError(f"unsupported preset schema: {payload.get('schema_version')!r}")
    return validate_state(state_from_dict(payload["state"]))
