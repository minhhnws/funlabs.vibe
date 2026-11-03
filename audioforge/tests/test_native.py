import subprocess
from pathlib import Path

import pytest

from audioforge.app.native import NativePipeWireHost, render_native_conf
from audioforge.app.state import create_default_state


def test_native_graph_detection_finds_owned_sink_and_output():
    status = "Audio\n  77. audioforge [vol: 1.00]\n  78. audioforge_output [Stream/Output/Audio]\n"

    def run(argv, **kwargs):
        assert argv == ["wpctl", "status"]
        return subprocess.CompletedProcess(argv, 0, status, "")

    from audioforge.app.native import detect_native_graph

    assert detect_native_graph(run, sink_name="audioforge") == ("77", "78")


def test_native_graph_detection_requires_owned_sink_and_output():
    status = "Audio\n  77. audioforge [vol: 1.00]\n"

    def run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, status, "")

    from audioforge.app.native import detect_native_graph

    assert detect_native_graph(run, sink_name="audioforge") is None


def test_native_conf_is_pipewire_factory_config_and_injects_state():
    state = create_default_state("Club")
    state.output_gain_db = 4.0
    state.modules["eq"].parameters.update(low_db=2.5, mid_db=-1.5, high_db=1.0, presence_db=3.0)
    rendered = render_native_conf(state, "audioforge_test")
    assert "libpipewire-module-filter-chain" in rendered
    assert "node.name = \"audioforge_test\"" in rendered
    assert "node.name = \"audioforge_test_output\"" in rendered
    assert '"Freq" = 90.0' in rendered
    assert '"Gain" = 2.5' in rendered
    assert '"Gain" = 4.0' in rendered
    assert not rendered.lstrip().startswith("{")


def test_native_host_restores_default_and_moves_streams(tmp_path: Path):
    calls = []

    class Proc:
        pid = 1234
        def poll(self): return None
        def terminate(self): calls.append(("terminate",))
        def wait(self, timeout=None): calls.append(("wait", timeout)); return 0
        def kill(self): calls.append(("kill",))

    def run(argv, **kwargs):
        calls.append(tuple(argv))
        if argv[:2] == ["wpctl", "get-volume"]:
            return subprocess.CompletedProcess(argv, 0, "Volume: 0.50\n", "")
        if argv[:2] == ["wpctl", "status"]:
            return subprocess.CompletedProcess(argv, 0, "Audio\n  77. audioforge_test [vol: 1.00]\n  78. audioforge_test_output [Stream/Output/Audio]\n  88. HDMI [vol: 1.00]\n", "")
        if argv[:2] == ["pactl", "list"]:
            return subprocess.CompletedProcess(argv, 0, "Sink Input #1481\n\tSink: 88\nSink Input #1482\n\tSink: 77\n", "")
        return subprocess.CompletedProcess(argv, 0, "", "")

    host = NativePipeWireHost(tmp_path, runner=run, popen=lambda *a, **k: Proc(), sink_name="audioforge_test")
    host.start(create_default_state())
    assert host.mode == "live"
    assert (tmp_path / "audioforge_test.conf").exists()
    assert any(cmd[:3] == ("wpctl", "set-default", "77") for cmd in calls)
    assert any(cmd[:3] == ("pactl", "move-sink-input", "1481") and cmd[3] == "audioforge_test" for cmd in calls)
    host.stop()
    assert host.mode == "direct-fallback"
    assert not (tmp_path / "audioforge_test.conf").exists()
    assert any(cmd[:3] == ("wpctl", "set-default", "88") for cmd in calls)
    assert any(item[0] == "terminate" for item in calls if isinstance(item, tuple))


def test_native_host_failure_keeps_fallback_and_cleans(tmp_path: Path):
    def run(argv, **kwargs):
        if argv[:2] == ["wpctl", "status"]:
            return subprocess.CompletedProcess(argv, 0, "Audio\n  88. HDMI [vol: 1.00]\n", "")
        raise FileNotFoundError(argv[0])

    host = NativePipeWireHost(tmp_path, runner=run, popen=lambda *a, **k: (_ for _ in ()).throw(OSError("pipewire")), sink_name="audioforge_fail")
    host.start(create_default_state())
    assert host.mode == "fallback"
    assert host.last_error
    assert not list(tmp_path.iterdir())


@pytest.mark.integration
def test_native_integration_smoke_opt_in():
    pytest.skip("run explicitly via audioforge/scripts/native-pipewire-smoke.py")
