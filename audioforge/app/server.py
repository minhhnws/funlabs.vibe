"""Local JSON control surface for AudioForge."""
from __future__ import annotations

import json
import mimetypes
import threading
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .analyzer import Analyzer
from .engine import EngineStatus, safe_fallback, set_bypass, start_engine
from .filter_chain import FilterChainManager
from .presets import load_preset, save_preset
from .state import AudioState, SnapshotState, create_default_state, create_profile_state, state_to_dict, validate_state

API_VERSION = "1.0"
STATE_SCHEMA_VERSION = 1
_UI_ROOT = Path(__file__).resolve().parents[1] / "ui"
_LOCALHOST_NAMES = {"localhost", "127.0.0.1", "::1"}
_EQ_PARAMS = {"low_db": (-12.0, 12.0), "mid_db": (-12.0, 12.0), "high_db": (-12.0, 12.0), "presence_db": (-12.0, 12.0)}
_DYNAMICS_PARAMS = {"threshold_db": (-60.0, 0.0), "ratio": (1.0, 20.0)}
_MODULE_PARAMS = {"eq": _EQ_PARAMS, "compressor": _DYNAMICS_PARAMS,
                  "preamp": {"gain_db": (-24.0, 12.0)},
                  "bass": {"gain_db": (-24.0, 12.0), "separation_hz": (20.0, 240.0)},
                  "saturation": {"amount": (0.0, 1.0)}, "imaging": {"width": (0.5, 1.5)},
                  "limiter": {"ceiling_db": (-12.0, -0.1)}}


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    return float(value)


def _boolean(value: Any, name: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{name} must be boolean")
    return value


def _bounded(value: Any, name: str, low: float, high: float) -> float:
    return min(high, max(low, _number(value, name)))


def _parameters(data: Any, allowed: dict[str, tuple[float, float]], label: str) -> dict[str, float]:
    if not isinstance(data, dict) or not data:
        raise ValueError(f"{label} parameters must be a non-empty object")
    unknown = set(data) - set(allowed)
    if unknown:
        raise ValueError(f"unknown {label} parameter: {sorted(unknown)[0]}")
    return {key: _bounded(value, f"{label}.{key}", *allowed[key]) for key, value in data.items()}


def _slot(value: Any) -> str:
    if value not in {"a", "b"} or type(value) is not str:
        raise ValueError("snapshot slot must be 'a' or 'b'")
    return value


class AudioForgeController:
    def __init__(self, preset_dir: str | Path | None = None, state: AudioState | None = None, chain_manager: FilterChainManager | None = None):
        self.state = validate_state(state or create_default_state())
        self.snapshots = SnapshotState()
        self.analyzer = Analyzer(self.state)
        self.preset_dir = Path(preset_dir or (Path.home() / ".local" / "share" / "audioforge" / "presets"))
        self.chain_manager = chain_manager
        self._lock = threading.RLock()
        self.status = self._status_from_engine(start_engine(self.state, chain_manager=chain_manager))

    def _status_from_engine(self, status: EngineStatus) -> dict[str, Any]:
        if status.mode == "fallback":
            mode = "fallback"
            label = "FALLBACK / Direct output"
        elif status.mode == "live" and status.filter_chain_available:
            mode = "live"
            label = "LIVE / PipeWire"
        else:
            mode = "simulation"
            label = "SIMULATION / PipeWire unavailable"
        if not status.filter_chain_available:
            self.state.bypass = True
        return {
            "mode": mode, "label": label, "reason": status.reason,
            "sink_name": status.sink_name, "sample_rate": status.sample_rate or self.state.sample_rate,
            "channels": status.channels, "channel_layout": status.channel_layout or self.state.channel_layout,
            "filter_chain_available": status.filter_chain_available,
            "bypass": self.state.bypass,
            "muted": self.state.muted,
            "protection": self.state.protection or status.reason,
        }

    def _enforce_safe_bypass(self) -> None:
        if not self.status.get("filter_chain_available", False):
            self.state.bypass = True
            self.status["bypass"] = True

    def _sync_chain(self) -> None:
        if self.chain_manager is not None:
            self.chain_manager.start(self.state, sink_name=self.status.get("sink_name"))
            self.status["filter_chain_available"] = self.chain_manager.mode == "live"
            if not self.status["filter_chain_available"]:
                self.state.bypass = True
                self.status["bypass"] = True

    def payload(self) -> dict[str, Any]:
        with self._lock:
            self._enforce_safe_bypass()
            frame = self.analyzer.next_frame()
            status = deepcopy(self.status)
            status.update({"bypass": self.state.bypass, "muted": self.state.muted,
                           "protection": self.state.protection or status.get("reason")})
            return {"api_version": API_VERSION, "state_schema_version": STATE_SCHEMA_VERSION,
                    "state": state_to_dict(self.state), "status": status, "analyzer": {
                "frame_index": frame.frame_index, "spectrum": frame.spectrum,
                "waveform_left": frame.waveform_left, "waveform_right": frame.waveform_right,
                "vu_left_db": frame.vu_left_db, "vu_right_db": frame.vu_right_db,
                "loudness_lufs": frame.loudness_lufs, "true_peak_db": frame.true_peak_db,
            }}

    def update(self, changes: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if not isinstance(changes, dict): raise ValueError("state payload must be an object")
            allowed = {"output_gain_db", "limiter_ceiling_db", "bypass", "muted", "routing", "latency_ms", "sample_rate", "channel_layout"}
            for key, value in changes.items():
                if key in allowed:
                    if key in {"bypass", "muted"}: value = _boolean(value, key)
                    elif key in {"output_gain_db", "limiter_ceiling_db", "latency_ms", "sample_rate"}: value = _number(value, key)
                    elif key in {"routing", "channel_layout"} and not isinstance(value, str): raise ValueError(f"{key} must be a string")
                    setattr(self.state, key, value)
                elif key == "modules" and isinstance(value, dict):
                    for module_name, module_data in value.items():
                        if module_name not in self.state.modules or not isinstance(module_data, dict):
                            raise ValueError(f"unknown module: {module_name}")
                        module = self.state.modules[module_name]
                        if "enabled" in module_data: module.enabled = _boolean(module_data["enabled"], "enabled")
                        if "parameters" in module_data:
                            if not isinstance(module_data["parameters"], dict): raise ValueError("parameters must be an object")
                            if module_name not in _MODULE_PARAMS: raise ValueError(f"module has no writable parameters: {module_name}")
                            module.parameters.update(_parameters(module_data["parameters"], _MODULE_PARAMS[module_name], module_name))
                else:
                    raise ValueError(f"unknown state field: {key}")
            self.state = validate_state(self.state)
            self.analyzer.state = self.state
            self._sync_chain()
            return self.payload()

    def profile(self, name: str) -> dict[str, Any]:
        if name not in {"Club", "Cinema"}: raise ValueError("profile must be Club or Cinema")
        with self._lock:
            old = self.state
            fresh = create_default_state(name)
            fresh.output_gain_db, fresh.limiter_ceiling_db, fresh.bypass, fresh.muted = old.output_gain_db, old.limiter_ceiling_db, old.bypass, old.muted
            self.state = fresh; self.analyzer.state = fresh
            self._sync_chain()
            return self.payload()

    def action(self, data: dict[str, Any]) -> dict[str, Any]:
        action = data.get("action")
        if action == "set_module":
            if not isinstance(data.get("module"), str): raise ValueError("module must be a string")
            return self.update({"modules": {data["module"]: {"enabled": data["enabled"]}}})
        if action == "set_gain": return self.update({"output_gain_db": _bounded(data.get("value", data.get("gain_db")), "gain", -24.0, 12.0)})
        if action == "set_bypass":
            value = _boolean(data["value"], "bypass")
            with self._lock:
                engine_status = set_bypass(self.state, value)
                if value is False and not engine_status.filter_chain_available:
                    self.state.bypass = True
                    self.status["reason"] = "No real filter chain available; safe bypass retained"
                else:
                    self.status = self._status_from_engine(engine_status)
            return self.payload()
        if action == "set_mute": return self.update({"muted": _boolean(data["value"], "muted")})
        if action == "set_eq": return self.update({"modules": {"eq": {"parameters": _parameters(data.get("parameters"), _EQ_PARAMS, "eq")}}})
        if action == "set_dynamics": return self.update({"modules": {"compressor": {"parameters": _parameters(data.get("parameters"), _DYNAMICS_PARAMS, "dynamics")}}})
        if action == "set_width": return self.update({"modules": {"imaging": {"parameters": {"width": _bounded(data["value"], "width", 0.5, 1.5)}}}})
        if action == "loudness_match":
            self.snapshots.loudness_match = _boolean(data.get("value", True), "loudness_match"); return self.payload()
        if action in {"snapshot_a", "snapshot_b"}:
            (self.snapshots.store_a if action.endswith("a") else self.snapshots.store_b)(self.state); return self.payload()
        if action == "compare_ab":
            slot = _slot(data.get("slot", "a")); self.state = validate_state(self.snapshots.restore_a() if slot == "a" else self.snapshots.restore_b()); self.analyzer.state = self.state; return self.payload()
        if action == "reset_safe":
            self.state = create_default_state(self.state.profile.name); self.state.bypass = True; self.state.muted = False; self.analyzer.state = self.state; return self.payload()
        if action == "save_preset":
            name = _preset_name(data.get("name")); self.preset_dir.mkdir(parents=True, exist_ok=True); save_preset(self.preset_dir / f"{name}.json", self.state); return self.payload()
        if action == "load_preset":
            name = _preset_name(data.get("name")); self.state = load_preset(self.preset_dir / f"{name}.json"); self.analyzer.state = self.state; return self.payload()
        raise ValueError(f"unknown action: {action}")


def _preset_name(value: Any) -> str:
    name = str(value or "").strip()
    if not name or name in {".", ".."} or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in name): raise ValueError("invalid preset name")
    return name


def create_server(host: str = "127.0.0.1", port: int = 8765, *, preset_dir: str | Path | None = None, controller: AudioForgeController | None = None, chain_manager: FilterChainManager | None = None) -> ThreadingHTTPServer:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("AudioForge API binds to localhost only")
    controller = controller or AudioForgeController(preset_dir=preset_dir, chain_manager=chain_manager)
    def allowed_origin(origin: str | None) -> str | None:
        if not origin: return None
        parsed = urlparse(origin)
        if parsed.scheme in {"http", "https"} and parsed.hostname in _LOCALHOST_NAMES and not parsed.username and not parsed.password and not parsed.path.rstrip("/") and not parsed.query and not parsed.fragment:
            return origin
        return None
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, payload: Any, content_type: str = "application/json"):
            raw = json.dumps(payload, separators=(",", ":")).encode()
            self.send_response(status); self.send_header("Content-Type", content_type); self.send_header("Content-Length", str(len(raw)))
            origin = allowed_origin(self.headers.get("Origin"))
            if origin:
                self.send_header("Access-Control-Allow-Origin", origin); self.send_header("Vary", "Origin")
            self.end_headers(); self.wfile.write(raw)
        def _send_bytes(self, raw: bytes, content_type: str):
            self.send_response(200); self.send_header("Content-Type", content_type); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
        def do_OPTIONS(self):
            self.send_response(204)
            origin = allowed_origin(self.headers.get("Origin"))
            if origin: self.send_header("Access-Control-Allow-Origin", origin); self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS"); self.send_header("Access-Control-Allow-Headers", "Content-Type"); self.end_headers()
        def do_GET(self):
            path = urlparse(self.path).path
            if path in {"/", "/index.html", "/styles.css", "/app.js"}:
                target = _UI_ROOT / ("index.html" if path in {"/", "/index.html"} else path.lstrip("/"))
                if target.is_file():
                    self._send_bytes(target.read_bytes(), mimetypes.guess_type(str(target))[0] or "application/octet-stream")
                    return
            if path == "/api/state": return self._send(200, controller.payload())
            if path == "/api/presets":
                controller.preset_dir.mkdir(parents=True, exist_ok=True); return self._send(200, {"presets": sorted(p.stem for p in controller.preset_dir.glob("*.json"))})
            if path == "/api/events":
                payload = controller.payload()
                raw = (f"event: status\ndata: {json.dumps({'type': 'status', 'data': payload['status']}, separators=(',', ':'))}\n\n"
                        f"event: analyzer\ndata: {json.dumps({'type': 'analyzer', 'data': payload['analyzer']}, separators=(',', ':'))}\n\n").encode()
                self.send_response(200); self.send_header("Content-Type", "text/event-stream; charset=utf-8"); self.send_header("Cache-Control", "no-cache"); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw); return
            self._send(404, {"error": {"code": "not_found", "message": "route not found"}})
        def do_POST(self):
            try:
                length = int(self.headers.get("Content-Length", "0")); data = json.loads(self.rfile.read(length) or b"{}")
                path = urlparse(self.path).path
                if not isinstance(data, dict): raise ValueError("JSON payload must be an object")
                if path == "/api/state": result = controller.update(data)
                elif path == "/api/profile": result = controller.profile(data.get("profile", data.get("name")))
                elif path == "/api/snapshot": result = controller.action({"action": f"snapshot_{_slot(data.get('slot', 'a'))}"})
                elif path == "/api/action": result = controller.action(data)
                else: return self._send(404, {"error": {"code": "not_found", "message": "route not found"}})
                self._send(200, result)
            except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as exc: self._send(400, {"error": {"code": "validation_error", "message": str(exc)}})
        def log_message(self, *_args): pass
    return ThreadingHTTPServer((host, port), Handler)
