"""Safe lifecycle for the first AudioForge PipeWire engine boundary."""
from __future__ import annotations

from dataclasses import dataclass

from .pipewire import PipeWireAdapter, discover_channel_layout, discover_default_sink
from .state import AudioState, validate_state


@dataclass(frozen=True)
class EngineStatus:
    mode: str
    reason: str | None = None
    sink_name: str | None = None
    sample_rate: int = 0
    channels: int = 0
    channel_layout: str = "unknown"
    downmix_required: bool = False
    stereo_widening: bool = False
    filter_chain_available: bool = False


def safe_fallback(state: AudioState, reason: str) -> EngineStatus:
    state.bypass = True
    state.routing = "direct-fallback"
    state.protection = reason
    return EngineStatus(mode="fallback", reason=reason, channel_layout=state.channel_layout)


def start_engine(state: AudioState, adapter: PipeWireAdapter | None = None, chain_manager=None) -> EngineStatus:
    """Discover first; only then release the safe startup bypass."""
    state.bypass = True
    try:
        checked = validate_state(state)
        state.__dict__.update(checked.__dict__)
        sink = discover_default_sink(adapter)
        if not sink.available:
            return safe_fallback(state, sink.reason or "PipeWire sink unavailable")
        layout = discover_channel_layout(adapter)
        if not layout.available:
            return safe_fallback(state, layout.reason or "PipeWire channel layout unavailable")
        state.sample_rate = sink.sample_rate or state.sample_rate
        state.channel_layout = layout.name
        state.routing = sink.name or "default-sink"
        state.protection = None
        filter_available = False
        if chain_manager is not None:
            chain_manager.start(state, sink_name=sink.name)
            filter_available = chain_manager.mode == "live"
        status = EngineStatus(
            mode="live", sink_name=sink.name, sample_rate=state.sample_rate,
            channels=layout.channels, channel_layout=layout.name,
            downmix_required=layout.downmix_required,
            stereo_widening=layout.stereo_widening,
            filter_chain_available=filter_available,
            reason=(getattr(chain_manager, "last_error", None) if chain_manager is not None else None),
        )
        if status.filter_chain_available:
            state.bypass = False
        return status
    except Exception as exc:  # device loss and malformed graphs are fail-safe
        return safe_fallback(state, f"engine start failed: {exc}")


def stop_engine(state: AudioState, chain_manager=None) -> EngineStatus:
    state.bypass = True
    if chain_manager is not None:
        chain_manager.stop()
    if state.routing == "direct-fallback":
        return EngineStatus(mode="fallback", reason=state.protection, channel_layout=state.channel_layout)
    state.routing = "default-sink"
    return EngineStatus(mode="bypassed", channel_layout=state.channel_layout)


def set_bypass(state: AudioState, bypass: bool) -> EngineStatus:
    state.bypass = bool(bypass)
    return EngineStatus(mode="bypassed" if state.bypass else "live", channel_layout=state.channel_layout)
