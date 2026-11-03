import pytest

from audioforge.app.state import (
    AudioState,
    ModuleState,
    SnapshotState,
    ValidationError,
    create_default_state,
    create_profile_state,
    state_from_dict,
    state_to_dict,
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


def test_chill_defaults_are_warm_controlled_and_not_club_loud():
    chill = create_default_state("Chill")
    assert chill.profile.name == "Chill"
    assert chill.profile.description == "Deep, controlled bass, warm low-mids, smooth highs, and relaxed dynamics."
    assert chill.modules["bass"].parameters == {"gain_db": 1.5, "separation_hz": 85.0}
    assert chill.modules["eq"].parameters == {"low_db": 1.0, "mid_db": 1.5, "high_db": -0.5, "presence_db": -0.5}
    assert chill.modules["compressor"].parameters == {"threshold_db": -24.0, "ratio": 1.6}
    assert chill.modules["saturation"].parameters["amount"] == 0.03
    assert chill.modules["imaging"].parameters["width"] == 1.08
    assert chill.modules["limiter"].parameters["ceiling_db"] == -2.0
    assert chill.limiter_ceiling_db == -2.0


def test_validation_bounds_gain_and_limiter_and_surfaces_protection():
    state = create_default_state()
    unsafe = AudioState(**{**state.__dict__, "output_gain_db": 99.0, "limiter_ceiling_db": 3.0})
    checked = validate_state(unsafe)
    assert checked.output_gain_db == 12.0
    assert checked.limiter_ceiling_db == -0.1
    assert checked.protection is not None


def test_validation_bounds_nested_gain_and_limiter_and_reports_protection():
    state = create_default_state()
    state.modules["preamp"].parameters["gain_db"] = 99.0
    state.modules["bass"].parameters["gain_db"] = -99.0
    state.modules["limiter"].parameters["ceiling_db"] = 3.0

    checked = validate_state(state)

    assert checked.modules["preamp"].parameters["gain_db"] == 12.0
    assert checked.modules["bass"].parameters["gain_db"] == -24.0
    assert checked.modules["limiter"].parameters["ceiling_db"] == -0.1
    assert checked.protection == (
        "preamp gain clamped; bass gain clamped; limiter module ceiling clamped"
    )


def test_ab_snapshots_are_deeply_isolated():
    state = create_default_state()
    snapshots = SnapshotState()
    snapshots.store_a(state)
    state.modules["bass"].parameters["gain_db"] = 9.0
    assert snapshots.a.modules["bass"].parameters["gain_db"] != 9.0
    restored = snapshots.restore_a()
    restored.modules["bass"].parameters["gain_db"] = -9.0
    assert snapshots.a.modules["bass"].parameters["gain_db"] != -9.0


def test_loudness_match_is_part_of_serialized_state_and_snapshots():
    state = create_default_state()
    state.loudness_match = True
    restored = state_from_dict(state_to_dict(state))
    assert restored.loudness_match is True
    snapshots = SnapshotState()
    snapshots.store_a(state)
    state.loudness_match = False
    assert snapshots.restore_a().loudness_match is True


def test_unknown_profile_is_rejected():
    with pytest.raises(ValueError):
        create_profile_state("Unknown")
