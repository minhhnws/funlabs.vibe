import pytest

from audioforge.app.state import (
    AudioState,
    ModuleState,
    SnapshotState,
    ValidationError,
    create_default_state,
    create_profile_state,
    validate_state,
)


def test_club_defaults_are_safe_and_dj_oriented():
    state = create_default_state("Club")
    assert state.profile.name == "Club"
    assert state.bypass is True
    assert state.muted is False
    assert state.modules["limiter"].enabled is True
    assert state.protection is None
    assert state.modules["bass"].parameters["gain_db"] > 0
    assert state.limiter_ceiling_db <= -1.0


def test_cinema_defaults_are_transparent_and_distinct():
    club = create_default_state("Club")
    cinema = create_default_state("Cinema")
    assert cinema.profile.name == "Cinema"
    assert cinema.modules["compressor"].parameters["ratio"] < club.modules["compressor"].parameters["ratio"]
    assert cinema.modules["imaging"].parameters["width"] < club.modules["imaging"].parameters["width"]


def test_validation_bounds_gain_and_limiter_and_surfaces_protection():
    state = create_default_state()
    unsafe = AudioState(**{**state.__dict__, "output_gain_db": 99.0, "limiter_ceiling_db": 3.0})
    checked = validate_state(unsafe)
    assert checked.output_gain_db == 12.0
    assert checked.limiter_ceiling_db == -0.1
    assert checked.protection is not None


def test_ab_snapshots_are_deeply_isolated():
    state = create_default_state()
    snapshots = SnapshotState()
    snapshots.store_a(state)
    state.modules["bass"].parameters["gain_db"] = 9.0
    assert snapshots.a.modules["bass"].parameters["gain_db"] != 9.0
    restored = snapshots.restore_a()
    restored.modules["bass"].parameters["gain_db"] = -9.0
    assert snapshots.a.modules["bass"].parameters["gain_db"] != -9.0


def test_unknown_profile_is_rejected():
    with pytest.raises(ValueError):
        create_profile_state("Unknown")
