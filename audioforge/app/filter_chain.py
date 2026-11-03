"""Structured PipeWire filter-chain generation with fail-safe lifecycle."""
from __future__ import annotations

import json
import math
import re
import subprocess
from pathlib import Path
from typing import Any, Protocol

from .state import AudioState, validate_state


MODULE_ORDER = ("preamp", "eq", "compressor", "saturation", "imaging", "limiter", "output")

class ValidatedFilterChainAdapter(Protocol):
    """Explicit integration boundary for a separately validated native adapter."""

    def create(self, config_path: Path) -> Any: ...
    def verify(self, node_id: str) -> Any: ...
    def destroy(self, node_id: str) -> Any: ...


def serialize_value(value: Any) -> str:
    """Serialize one config value without interpolation or non-finite numbers."""
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(float(value)):
            raise ValueError("config values must be finite")
        return json.dumps(value)
    raise TypeError(f"unsupported config value: {type(value).__name__}")


def _module(state: AudioState, name: str, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    source = state.modules.get(name)
    return {
        "name": name,
        "enabled": bool(source.enabled) if source else True,
        "parameters": dict(parameters if parameters is not None else (source.parameters if source else {})),
    }


def generate_filter_chain(state: AudioState, *, sink_name: str | None = None) -> dict[str, Any]:
    """Build a JSON-shaped, structured chain; no shell or config interpolation occurs."""
    checked = validate_state(state)
    modules = [
        _module(checked, "preamp"),
        _module(checked, "eq"),
        _module(checked, "compressor"),
        _module(checked, "saturation"),
    ]
    imaging = _module(checked, "imaging", {
        **(checked.modules.get("imaging").parameters if checked.modules.get("imaging") else {}),
        "mode": "stereo" if checked.channel_layout == "stereo" else "channel-safe",
    })
    if checked.channel_layout != "stereo":
        imaging["enabled"] = False
    modules.append(imaging)
    modules.extend([
        _module(checked, "limiter", {"ceiling_db": checked.limiter_ceiling_db}),
        {"name": "output", "enabled": True, "parameters": {"gain_db": checked.output_gain_db}},
    ])
    config: dict[str, Any] = {
        "version": 1,
        "channel_layout": checked.channel_layout,
        "properties": {"target.object": sink_name} if sink_name is not None else {},
        "chain": modules,
    }
    # Round-trip through JSON validates every leaf is serializable and finite.
    json.dumps(config, ensure_ascii=False, allow_nan=False)
    return config


def render_filter_chain_conf(state: AudioState, *, sink_name: str | None = None) -> str:
    """Render deterministic local config consumed by the bridge and diagnostics."""
    return json.dumps(generate_filter_chain(state, sink_name=sink_name), indent=2, ensure_ascii=False, allow_nan=False) + "\n"


class FilterChainManager:
    """Own the inspection config and an optional validated native node adapter."""

    def __init__(self, config_dir: str | Path, *, adapter: Any | None = None, engine_supported: bool = False):
        self.config_dir = Path(config_dir)
        # engine_supported is retained for API compatibility, but cannot opt in
        # to live mode. Only an explicitly supplied, validated adapter may do so.
        self.adapter = adapter
        self.engine_supported = engine_supported
        self.config_path: Path | None = None
        self.node_id: str | None = None
        self.mode = "simulation"
        self.last_error: str | None = None

    @staticmethod
    def _run_command(argv: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(argv, capture_output=True, text=True, check=False)

    @staticmethod
    def _object_id(stdout: str) -> str | None:
        for pattern in (r"(?m)^\s*id\s*[:=]\s*(\d+)\b", r"(?m)\bobject\s+(\d+)\b"):
            match = re.search(pattern, stdout)
            if match:
                return match.group(1)
        return None

    @classmethod
    def _checked_result(cls, result: Any, operation: str) -> tuple[str, str]:
        if result is True:
            raise RuntimeError(f"{operation} returned no verifiable result")
        returncode = getattr(result, "returncode", None)
        stdout = str(getattr(result, "stdout", "") or "")
        stderr = str(getattr(result, "stderr", "") or "")
        if returncode != 0 or stderr.strip():
            detail = stderr.strip() or stdout.strip() or f"exit code {returncode}"
            raise RuntimeError(f"{operation} failed: {detail}")
        return stdout, stderr

    def start(self, state: AudioState, *, sink_name: str | None = None) -> Path:
        self.stop()
        if self.adapter is not None and hasattr(self.adapter, "start"):
            path = self.adapter.start(state, sink_name=sink_name)
            self.config_path = Path(path) if path else None
            self.mode = getattr(self.adapter, "mode", "fallback")
            self.node_id = getattr(self.adapter, "virtual_id", None)
            self.last_error = getattr(self.adapter, "last_error", None)
            return self.config_path or self.config_dir / "audioforge-native.conf"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.config_dir / "audioforge-filter-chain.json"
        self.config_path.write_text(render_filter_chain_conf(state, sink_name=sink_name), encoding="utf-8")
        config_path = self.config_path
        if self.adapter is None:
            self.mode = "simulation"
            return config_path
        try:
            result = self.adapter.create(self.config_path)
            output, _ = self._checked_result(result, "filter-chain creation")
            candidate = self._object_id(output)
            if candidate is None:
                raise RuntimeError("filter-chain creation returned no valid object ID")
            verification = self.adapter.verify(candidate)
            graph_output, _ = self._checked_result(verification, "filter-chain graph verification")
            verified_id = self._object_id(graph_output)
            if verified_id != candidate:
                raise RuntimeError(f"graph verification did not confirm object {candidate}")
            self.node_id = candidate
            self.mode = "live"
            self.last_error = None
        except (OSError, subprocess.SubprocessError, ValueError, RuntimeError) as exc:
            self.node_id = None
            self.mode = "fallback"
            self.last_error = str(exc)
            if self.config_path and self.config_path.exists():
                self.config_path.unlink()
            self.config_path = None
        return config_path

    def stop(self) -> None:
        if self.adapter is not None and hasattr(self.adapter, "start"):
            self.adapter.stop()
            self.node_id = None
            self.config_path = None
            self.mode = "direct-fallback"
            return
        if self.node_id:
            try:
                if self.adapter is not None:
                    self.adapter.destroy(self.node_id)
            except (OSError, subprocess.SubprocessError):
                pass
        self.node_id = None
        if self.config_path and self.config_path.exists():
            self.config_path.unlink()
        self.config_path = None
        self.mode = "direct-fallback"
