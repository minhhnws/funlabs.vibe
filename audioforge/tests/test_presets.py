import json

import pytest

from audioforge.app.presets import PRESET_VERSION, PresetVersionError, load_preset, save_preset
from audioforge.app.state import create_default_state


def test_preset_round_trip(tmp_path):
    path = tmp_path / "club.json"
    original = create_default_state("Club")
    save_preset(path, original)
    loaded = load_preset(path)
    assert loaded == original
    assert json.loads(path.read_text())["schema_version"] == PRESET_VERSION


def test_preset_version_is_rejected(tmp_path):
    path = tmp_path / "future.json"
    path.write_text(json.dumps({"schema_version": PRESET_VERSION + 1, "state": {}}))
    with pytest.raises(PresetVersionError):
        load_preset(path)
