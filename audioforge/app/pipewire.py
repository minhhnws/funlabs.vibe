"""Read-only PipeWire graph discovery behind an injectable subprocess boundary."""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence


Runner = Callable[[Sequence[str]], Any]


@dataclass(frozen=True)
class SinkInfo:
    name: str | None = None
    object_id: int | str | None = None
    sample_rate: int = 0
    channels: int = 0
    available: bool = False
    status: str = "unavailable"
    reason: str | None = None


@dataclass(frozen=True)
class ChannelLayout:
    name: str = "unknown"
    channels: int = 0
    positions: tuple[str, ...] = ()
    downmix_required: bool = False
    stereo_widening: bool = False
    available: bool = False
    status: str = "unavailable"
    reason: str | None = None


@dataclass
class PipeWireAdapter:
    """PipeWire discovery adapter; it never mutates the graph."""

    runner: Runner | None = None
    command: tuple[str, ...] = ("pw-dump",)
    commands: list[list[str]] = field(default_factory=list)

    def run_dump(self) -> Any:
        return self.run_command(self.command)

    def run_command(self, command: Sequence[str]) -> Any:
        argv = list(command)
        self.commands.append(argv)
        if self.runner is not None:
            return self.runner(argv)
        return subprocess.run(argv, capture_output=True, text=True, check=True)

    def dump(self) -> list[dict[str, Any]]:
        result = self.run_dump()
        if hasattr(result, "stdout"):
            result = result.stdout
        if isinstance(result, bytes):
            result = result.decode("utf-8")
        payload = json.loads(result)
        if not isinstance(payload, list):
            raise ValueError("pw-dump payload is not a list")
        return [item for item in payload if isinstance(item, dict)]


def _props(item: dict[str, Any]) -> dict[str, Any]:
    info = item.get("info") or {}
    props = info.get("props") or item.get("props") or {}
    return props if isinstance(props, dict) else {}


def _nodes(adapter: PipeWireAdapter) -> list[dict[str, Any]]:
    return adapter.dump()


def _discovery_error(prefix: str, exc: Exception) -> str:
    """Keep subprocess diagnostics visible while preserving a stable prefix."""
    detail = getattr(exc, "stderr", None) or str(exc)
    return f"{prefix}: {detail}"


def _pactl_default_sink(adapter: PipeWireAdapter) -> str | None:
    result = adapter.run_command(("pactl", "get-default-sink"))
    if hasattr(result, "stdout"):
        result = result.stdout
    if isinstance(result, bytes):
        result = result.decode("utf-8")
    if not isinstance(result, str):
        return None
    name = result.strip().splitlines()[0] if result.strip() else ""
    return name or None


def discover_default_sink(adapter: PipeWireAdapter | None = None) -> SinkInfo:
    adapter = adapter or PipeWireAdapter()
    try:
        items = _nodes(adapter)
        sinks = []
        default_name = None
        for item in items:
            props = _props(item)
            if props.get("metadata.name") == "default":
                default_name = props.get("metadata.default.audio.sink") or props.get("default.audio.sink")
            media_class = str(props.get("media.class", ""))
            if media_class in {"Audio/Sink", "Audio/Duplex"}:
                sinks.append((item, props))
        chosen = next((pair for pair in sinks if pair[1].get("node.name") == default_name), None)
        if chosen is None:
            try:
                pactl_name = _pactl_default_sink(adapter)
            except (FileNotFoundError, subprocess.CalledProcessError, OSError, ValueError, TypeError):
                pactl_name = None
            chosen = next((pair for pair in sinks if pair[1].get("node.name") == pactl_name), None)
        if chosen is None and len(sinks) == 1:
            chosen = sinks[0]
        if chosen is None:
            return SinkInfo(status="fallback", reason="default PipeWire sink unavailable")
        item, props = chosen
        params = (item.get("info") or {}).get("params") or {}
        formats = params.get("Format", []) if isinstance(params, dict) else []
        fmt = formats[0] if formats and isinstance(formats[0], dict) else {}
        rate = props.get("audio.rate", props.get("audio.format.rate", fmt.get("rate", 0)))
        channels = props.get("audio.channels", props.get("audio.format.channels", fmt.get("channels", 0)))
        return SinkInfo(
            name=str(props.get("node.name")), object_id=item.get("id"),
            sample_rate=int(str(rate).split("/")[0]), channels=int(channels),
            available=True, status="available",
        )
    except FileNotFoundError as exc:
        return SinkInfo(status="unavailable", reason=f"pw-dump unavailable: {exc}")
    except (subprocess.CalledProcessError, OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return SinkInfo(status="unavailable", reason=_discovery_error("PipeWire discovery failed", exc))


def discover_channel_layout(adapter: PipeWireAdapter | None = None) -> ChannelLayout:
    adapter = adapter or PipeWireAdapter()
    try:
        sink = discover_default_sink(adapter)
        if not sink.available:
            return ChannelLayout(status=sink.status, reason=sink.reason)
        items = _nodes(adapter)
        sink_item = next((item for item in items if _props(item).get("node.name") == sink.name), {})
        if not sink_item:
            return ChannelLayout(status="fallback", reason="default PipeWire sink disappeared during layout discovery")
        props = _props(sink_item)
        params = (sink_item.get("info") or {}).get("params") or {}
        formats = params.get("Format", []) if isinstance(params, dict) else []
        fmt = formats[0] if formats and isinstance(formats[0], dict) else {}
        raw_positions = props.get("audio.position", fmt.get("position", ""))
        if isinstance(raw_positions, (list, tuple)):
            positions = tuple(str(value) for value in raw_positions)
        else:
            positions = tuple(str(raw_positions).replace(",", " ").replace("[", "").replace("]", "").split())
        channels = sink.channels or len(positions)
        if channels == 2:
            name = "stereo"
        elif channels == 6 and set(positions) >= {"FL", "FR", "FC", "LFE", "RL", "RR"}:
            name = "5.1"
        else:
            name = f"{channels}-channel" if channels else "unknown"
        return ChannelLayout(
            name=name, channels=channels, positions=positions,
            downmix_required=channels == 2, stereo_widening=False,
            available=True, status="available",
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return ChannelLayout(status="unavailable", reason=_discovery_error("PipeWire layout discovery failed", exc))
