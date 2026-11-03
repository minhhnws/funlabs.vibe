"""Reversible native PipeWire filter-chain host."""
from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path
from typing import Callable, Any

from .state import AudioState, validate_state


Runner = Callable[..., subprocess.CompletedProcess[str]]


def detect_native_graph(
    runner: Runner = subprocess.run, *, sink_name: str = "audioforge"
) -> tuple[str, str] | None:
    """Return owned native sink/output IDs only when both graph nodes exist."""
    try:
        result = runner(["wpctl", "status"], capture_output=True, text=True, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode:
        return None

    def node_id(name: str) -> str | None:
        pattern = re.compile(r"\b(\d+)\.\s+" + re.escape(name) + r"(?:\s|\[|$)")
        for line in result.stdout.splitlines():
            match = pattern.search(line)
            if match:
                return match.group(1)
        return None

    sink_id = node_id(sink_name)
    output_id = node_id(sink_name + "_output")
    return (sink_id, output_id) if sink_id and output_id else None


def _gain(state: AudioState, module: str, key: str, default: float = 0.0) -> float:
    value = state.modules.get(module)
    return float(value.parameters.get(key, default)) if value else default


def _enabled(state: AudioState, module: str) -> bool:
    return bool(state.modules.get(module).enabled) if module in state.modules else True


def render_native_conf(state: AudioState, sink_name: str) -> str:
    """Render the standalone PipeWire config used by ``pipewire -c``."""
    checked = validate_state(state)
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", sink_name):
        raise ValueError("native sink name contains unsupported characters")
    eq = checked.modules.get("eq")
    eqp = eq.parameters if eq else {}
    bands = [("bass", 90.0, 0.7, _gain(checked, "bass", "gain_db", 0.0)),
             ("lowmid", 220.0, 1.0, float(eqp.get("low_db", 0.0))),
             ("mid", 1200.0, 0.9, float(eqp.get("mid_db", 0.0))),
             ("presence", 3200.0, 0.8, float(eqp.get("presence_db", 0.0))),
             ("air", 9000.0, 0.7, float(eqp.get("high_db", 0.0)))]
    nodes = []
    links = []
    previous = None
    for name, freq, q, gain in bands:
        if name == "bass": label = "bq_lowshelf"
        elif name == "air": label = "bq_highshelf"
        else: label = "bq_peaking"
        nodes.append(f'            {{ type = builtin name = {name} label = {label} control = {{ "Freq" = {freq} "Q" = {q} "Gain" = {gain} }} }}')
        if previous:
            links.append(f'            {{ output = "{previous}:Out" input = "{name}:In" }}')
        previous = name
    nodes.append(f'            {{ type = builtin name = output label = bq_peaking control = {{ "Freq" = 1000.0 "Q" = 0.7 "Gain" = {checked.output_gain_db} }} }}')
    links.append(f'            {{ output = "{previous}:Out" input = "output:In" }}')
    graph = "\n".join(nodes) + "\n          ]\n          links = [\n" + "\n".join(links) + "\n          ]"
    return f'''context.properties = {{ log.level = 0 }}
context.spa-libs = {{ audio.convert.* = audioconvert/libspa-audioconvert support.* = support/libspa-support }}
context.modules = [
  {{ name = libpipewire-module-rt args = {{ rtportal.enabled = false }} flags = [ ifexists nofail ] }}
  {{ name = libpipewire-module-protocol-native }}
  {{ name = libpipewire-module-client-node }}
  {{ name = libpipewire-module-adapter }}
  {{ name = libpipewire-module-filter-chain args = {{
    node.description = "AudioForge {sink_name}"
    media.name = "AudioForge {sink_name}"
    filter.graph = {{ nodes = [
{graph}
        }}
    audio.channels = 2
    audio.position = [ FL FR ]
    capture.props = {{ node.name = "{sink_name}" node.description = "AudioForge {sink_name}" media.class = Audio/Sink priority.session = 2000 }}
    playback.props = {{ node.name = "{sink_name}_output" node.description = "AudioForge output" node.passive = true }}
  }} }}
]
'''


class NativePipeWireHost:
    """Own a child PipeWire process and restore all routing it changed."""
    def __init__(self, config_dir: str | Path, *, runner: Runner | None = None,
                 popen: Callable[..., Any] = subprocess.Popen, sink_name: str = "audioforge"):
        self.config_dir = Path(config_dir)
        self.runner = runner or subprocess.run
        self.popen = popen
        self.sink_name = sink_name
        self.config_path: Path | None = None
        self.process: Any | None = None
        self.virtual_id: str | None = None
        self.virtual_output_id: str | None = None
        self.original_sink: str | None = None
        self.moved_inputs: list[tuple[str, str]] = []
        self.mode = "direct-fallback"
        self.last_error: str | None = None

    def _run(self, argv: list[str]) -> subprocess.CompletedProcess[str]:
        return self.runner(argv, capture_output=True, text=True, check=False)

    def _status(self) -> str:
        result = self._run(["wpctl", "status"])
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or "wpctl status failed")
        return result.stdout

    def _capture_default(self, status: str) -> str | None:
        configured = None
        for line in status.splitlines():
            match = re.search(r"Audio/Sink\s+(\S+)", line)
            if match:
                configured = match.group(1)
                break
        if configured:
            value = self._verify_named_id(status, configured)
            if value:
                return value
        for line in status.splitlines():
            match = re.search(r"\b(\d+)\.\s+([^\[]+)\s+\[vol:", line)
            if match and self.sink_name not in line:
                return match.group(1)
        result = self._run(["pactl", "get-default-sink"])
        if result.returncode == 0 and result.stdout.strip():
            name = result.stdout.strip().splitlines()[0].strip()
            return self._verify_named_id(status, name) or name
        return None

    def _verify_id(self, status: str) -> str | None:
        return self._verify_named_id(status, self.sink_name)

    @staticmethod
    def _verify_named_id(status: str, name: str) -> str | None:
        pattern = re.compile(r"\b(\d+)\.\s+" + re.escape(name) + r"(?:\s|\[|$)")
        for line in status.splitlines():
            match = pattern.search(line)
            if match:
                return match.group(1)
        return None

    def _verify_graph(self, status: str) -> tuple[str | None, str | None]:
        return self._verify_id(status), self._verify_named_id(status, self.sink_name + "_output")

    def _sink_inputs(self) -> list[tuple[str, str]]:
        result = self._run(["pactl", "list", "sink-inputs"])
        if result.returncode:
            return []
        found = []
        current = None
        for line in result.stdout.splitlines():
            match = re.match(r"Sink Input #(\d+)", line)
            if match: current = match.group(1)
            match = re.search(r"\bSink:\s*(\d+)", line)
            if current and match:
                found.append((current, match.group(1))); current = None
        return found

    def _ctl(self, argv: list[str]) -> None:
        result = self._run(argv)
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or "command failed: " + " ".join(argv))

    def start(self, state: AudioState, *, sink_name: str | None = None) -> Path:
        self.stop()
        if sink_name:
            # target sink is not used as an identifier; the native name stays owned and safe.
            pass
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.config_dir / f"{self.sink_name}.conf"
        try:
            initial = self._status()
            self.original_sink = self._capture_default(initial)
            self.config_path.write_text(render_native_conf(state, self.sink_name), encoding="utf-8")
            self.process = self.popen(["pipewire", "-c", str(self.config_path)], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise RuntimeError("native pipewire process exited")
                virtual_id, output_id = self._verify_graph(self._status())
                if virtual_id and output_id:
                    self.virtual_id, self.virtual_output_id = virtual_id, output_id
                    break
                time.sleep(0.05)
            if not self.virtual_id:
                raise RuntimeError("native virtual sink did not appear in PipeWire graph")
            self._ctl(["wpctl", "set-default", self.virtual_id])
            for input_id, sink_id in self._sink_inputs():
                if sink_id != self.virtual_id:
                    self._ctl(["pactl", "move-sink-input", input_id, self.sink_name])
                    self.moved_inputs.append((input_id, sink_id))
            self.mode = "live"
            self.last_error = None
            return self.config_path
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            self.last_error = str(exc)
            self.mode = "fallback"
            self.stop()
            self.mode = "fallback"
            return self.config_path if self.config_path else self.config_dir / f"{self.sink_name}.conf"

    def stop(self) -> None:
        for input_id, sink_id in reversed(self.moved_inputs):
            try: self._ctl(["pactl", "move-sink-input", input_id, sink_id])
            except (OSError, RuntimeError, subprocess.SubprocessError, KeyboardInterrupt): pass
        self.moved_inputs.clear()
        if self.original_sink:
            try: self._ctl(["wpctl", "set-default", self.original_sink])
            except (OSError, RuntimeError, subprocess.SubprocessError, KeyboardInterrupt): pass
        if self.process is not None:
            try:
                self.process.terminate(); self.process.wait(timeout=2)
            except Exception:
                try: self.process.kill(); self.process.wait(timeout=2)
                except Exception: pass
        self.process = None
        self.virtual_id = None
        self.virtual_output_id = None
        if self.config_path and self.config_path.exists(): self.config_path.unlink()
        self.config_path = None
        self.original_sink = None
        self.mode = "direct-fallback"
