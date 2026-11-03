"""Local JSON control surface for AudioForge."""
from __future__ import annotations

import json
import threading
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .analyzer import Analyzer
from .engine import EngineStatus, safe_fallback, set_bypass, start_engine
from .presets import load_preset, save_preset
from .state import AudioState, SnapshotState, create_default_state, create_profile_state, state_to_dict, validate_state


class AudioForgeController:
    def __init__(self, preset_dir: str | Path | None = None, state: AudioState | None = None):
        self.state = validate_state(state or create_default_state())
        self.snapshots = SnapshotState()
        self.analyzer = Analyzer(self.state)
        self.preset_dir = Path(preset_dir or (Path.home() / ".local" / "share" / "audioforge" / "presets"))
        self._lock = threading.RLock()
        self.status = self._status_from_engine(start_engine(self.state))

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
        return {
            "mode": mode, "label": label, "reason": status.reason,
            "sink_name": status.sink_name, "sample_rate": status.sample_rate or self.state.sample_rate,
            "channels": status.channels, "channel_layout": status.channel_layout or self.state.channel_layout,
            "filter_chain_available": status.filter_chain_available,
        }

    def payload(self) -> dict[str, Any]:
        with self._lock:
            frame = self.analyzer.next_frame()
            return {"state": state_to_dict(self.state), "status": deepcopy(self.status), "analyzer": {
                "frame_index": frame.frame_index, "spectrum": frame.spectrum,
                "waveform_left": frame.waveform_left, "waveform_right": frame.waveform_right,
                "vu_left_db": frame.vu_left_db, "vu_right_db": frame.vu_right_db,
                "loudness_lufs": frame.loudness_lufs, "true_peak_db": frame.true_peak_db,
            }}

    def update(self, changes: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            allowed = {"output_gain_db", "limiter_ceiling_db", "bypass", "muted", "routing", "latency_ms", "sample_rate", "channel_layout"}
            for key, value in changes.items():
                if key in allowed:
                    setattr(self.state, key, value)
                elif key == "modules" and isinstance(value, dict):
                    for module_name, module_data in value.items():
                        if module_name not in self.state.modules or not isinstance(module_data, dict):
                            raise ValueError(f"unknown module: {module_name}")
                        module = self.state.modules[module_name]
                        if "enabled" in module_data: module.enabled = bool(module_data["enabled"])
                        if "parameters" in module_data:
                            module.parameters.update(module_data["parameters"])
                else:
                    raise ValueError(f"unknown state field: {key}")
            self.state = validate_state(self.state)
            self.analyzer.state = self.state
            return self.payload()

    def profile(self, name: str) -> dict[str, Any]:
        if name not in {"Club", "Cinema"}: raise ValueError("profile must be Club or Cinema")
        with self._lock:
            old = self.state
            fresh = create_default_state(name)
            fresh.output_gain_db, fresh.limiter_ceiling_db, fresh.bypass, fresh.muted = old.output_gain_db, old.limiter_ceiling_db, old.bypass, old.muted
            self.state = fresh; self.analyzer.state = fresh
            return self.payload()

    def action(self, data: dict[str, Any]) -> dict[str, Any]:
        action = data.get("action")
        if action == "set_module":
            return self.update({"modules": {data["module"]: {"enabled": data["enabled"]}}})
        if action == "set_gain": return self.update({"output_gain_db": data.get("value", data.get("gain_db"))})
        if action == "set_bypass":
            with self._lock: self.status = self._status_from_engine(set_bypass(self.state, bool(data["value"])))
            return self.payload()
        if action == "set_mute": return self.update({"muted": bool(data["value"])})
        if action == "set_eq": return self.update({"modules": {"eq": {"parameters": data.get("parameters", {})}}})
        if action == "set_dynamics": return self.update({"modules": {"compressor": {"parameters": data.get("parameters", {})}}})
        if action == "set_width": return self.update({"modules": {"imaging": {"parameters": {"width": data["value"]}}}})
        if action == "loudness_match":
            self.snapshots.loudness_match = bool(data.get("value", True)); return self.payload()
        if action in {"snapshot_a", "snapshot_b"}:
            (self.snapshots.store_a if action.endswith("a") else self.snapshots.store_b)(self.state); return self.payload()
        if action == "compare_ab":
            slot = data.get("slot", "a"); self.state = validate_state(self.snapshots.restore_a() if slot == "a" else self.snapshots.restore_b()); self.analyzer.state = self.state; return self.payload()
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


def create_server(host: str = "127.0.0.1", port: int = 8765, *, preset_dir: str | Path | None = None, controller: AudioForgeController | None = None) -> ThreadingHTTPServer:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("AudioForge API binds to localhost only")
    controller = controller or AudioForgeController(preset_dir=preset_dir)
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, payload: Any, content_type: str = "application/json"):
            raw = json.dumps(payload, separators=(",", ":")).encode()
            self.send_response(status); self.send_header("Content-Type", content_type); self.send_header("Content-Length", str(len(raw)))
            origin = self.headers.get("Origin", "")
            parsed_origin = urlparse(origin)
            if parsed_origin.scheme == "http" and parsed_origin.hostname in {"localhost", "127.0.0.1", "::1"}:
                self.send_header("Access-Control-Allow-Origin", origin)
            self.end_headers(); self.wfile.write(raw)
        def do_OPTIONS(self):
            self.send_response(204); self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS"); self.send_header("Access-Control-Allow-Headers", "Content-Type"); self.end_headers()
        def do_GET(self):
            path = urlparse(self.path).path
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
                if path == "/api/state": result = controller.update(data)
                elif path == "/api/profile": result = controller.profile(data.get("profile", data.get("name")))
                elif path == "/api/snapshot": result = controller.action({"action": f"snapshot_{data.get('slot', 'a')}"})
                elif path == "/api/action": result = controller.action(data)
                else: return self._send(404, {"error": {"code": "not_found", "message": "route not found"}})
                self._send(200, result)
            except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as exc: self._send(400, {"error": {"code": "validation_error", "message": str(exc)}})
        def log_message(self, *_args): pass
    return ThreadingHTTPServer((host, port), Handler)
