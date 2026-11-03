"""Typed, safe application state for AudioForge."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

MIN_OUTPUT_GAIN_DB = -24.0
MAX_OUTPUT_GAIN_DB = 12.0
MIN_LIMITER_CEILING_DB = -12.0
MAX_LIMITER_CEILING_DB = -0.1


@dataclass
class ModuleState:
    name: str
    enabled: bool = True
    parameters: dict[str, float | str | bool] = field(default_factory=dict)


@dataclass
class ProfileState:
    name: str
    description: str


@dataclass
class AudioState:
    profile: ProfileState
    modules: dict[str, ModuleState]
    output_gain_db: float = 0.0
    limiter_ceiling_db: float = -1.0
    bypass: bool = True
    muted: bool = False
    protection: str | None = None
    routing: str = "default-sink"
    latency_ms: float = 0.0
    sample_rate: int = 48000
    channel_layout: str = "stereo"


class ValidationError(ValueError):
    """Raised when state has an invalid non-bounded value."""


def create_profile_state(name: str) -> ProfileState:
    if name == "Club":
        return ProfileState(name, "Controlled bass punch, bus glue, and spacious highs.")
    if name == "Cinema":
        return ProfileState(name, "Transparent dialogue support with preserved dynamics.")
    raise ValueError(f"unknown profile: {name}")


def _modules_for(name: str) -> dict[str, ModuleState]:
    if name == "Club":
        return {
            "preamp": ModuleState("preamp", parameters={"gain_db": 0.0}),
            "bass": ModuleState("bass", parameters={"gain_db": 3.0, "separation_hz": 100.0}),
            "eq": ModuleState("eq", parameters={"presence_db": 0.0}),
            "compressor": ModuleState("compressor", parameters={"threshold_db": -18.0, "ratio": 2.5}),
            "saturation": ModuleState("saturation", parameters={"amount": 0.12}),
            "imaging": ModuleState("imaging", parameters={"width": 1.12}),
            "limiter": ModuleState("limiter", parameters={"ceiling_db": -1.0}),
        }
    if name == "Cinema":
        return {
            "preamp": ModuleState("preamp", parameters={"gain_db": 0.0}),
            "bass": ModuleState("bass", parameters={"gain_db": 1.0, "separation_hz": 90.0}),
            "eq": ModuleState("eq", parameters={"presence_db": 1.5}),
            "compressor": ModuleState("compressor", parameters={"threshold_db": -24.0, "ratio": 1.4}),
            "saturation": ModuleState("saturation", parameters={"amount": 0.02}),
            "imaging": ModuleState("imaging", parameters={"width": 1.04}),
            "limiter": ModuleState("limiter", parameters={"ceiling_db": -1.5}),
        }
    raise ValueError(f"unknown profile: {name}")


def create_default_state(profile: str = "Club") -> AudioState:
    return AudioState(profile=create_profile_state(profile), modules=_modules_for(profile))


def validate_state(state: AudioState) -> AudioState:
    """Return a safe state, clamping bounded controls and reporting protection."""
    if state.sample_rate <= 0:
        raise ValidationError("sample_rate must be positive")
    if state.latency_ms < 0:
        raise ValidationError("latency_ms cannot be negative")
    violations: list[str] = []
    gain = min(MAX_OUTPUT_GAIN_DB, max(MIN_OUTPUT_GAIN_DB, float(state.output_gain_db)))
    ceiling = min(MAX_LIMITER_CEILING_DB, max(MIN_LIMITER_CEILING_DB, float(state.limiter_ceiling_db)))
    if gain != state.output_gain_db:
        violations.append("output gain clamped")
    if ceiling != state.limiter_ceiling_db:
        violations.append("limiter ceiling clamped")
    checked = deepcopy(state)
    checked.output_gain_db = gain
    checked.limiter_ceiling_db = ceiling
    checked.protection = "; ".join(violations) if violations else state.protection
    checked.modules.setdefault("limiter", ModuleState("limiter", parameters={"ceiling_db": ceiling}))
    checked.modules["limiter"].enabled = True
    checked.modules["limiter"].parameters["ceiling_db"] = ceiling
    return checked


@dataclass
class SnapshotState:
    a: AudioState | None = None
    b: AudioState | None = None
    loudness_match: bool = False

    def store_a(self, state: AudioState) -> None:
        self.a = deepcopy(state)

    def store_b(self, state: AudioState) -> None:
        self.b = deepcopy(state)

    def restore_a(self) -> AudioState:
        if self.a is None:
            raise ValueError("snapshot A is empty")
        return deepcopy(self.a)

    def restore_b(self) -> AudioState:
        if self.b is None:
            raise ValueError("snapshot B is empty")
        return deepcopy(self.b)


def state_to_dict(state: AudioState) -> dict[str, Any]:
    return {
        "profile": {"name": state.profile.name, "description": state.profile.description},
        "modules": {k: {"name": v.name, "enabled": v.enabled, "parameters": v.parameters} for k, v in state.modules.items()},
        "output_gain_db": state.output_gain_db,
        "limiter_ceiling_db": state.limiter_ceiling_db,
        "bypass": state.bypass,
        "muted": state.muted,
        "protection": state.protection,
        "routing": state.routing,
        "latency_ms": state.latency_ms,
        "sample_rate": state.sample_rate,
        "channel_layout": state.channel_layout,
    }


def state_from_dict(data: dict[str, Any]) -> AudioState:
    profile_data = data["profile"]
    modules = {k: ModuleState(v["name"], v["enabled"], dict(v["parameters"])) for k, v in data["modules"].items()}
    return AudioState(ProfileState(profile_data["name"], profile_data["description"]), modules, **{k: data[k] for k in ("output_gain_db", "limiter_ceiling_db", "bypass", "muted", "protection", "routing", "latency_ms", "sample_rate", "channel_layout")})
