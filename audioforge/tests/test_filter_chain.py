import json
import subprocess
from pathlib import Path

import pytest

from audioforge.app.filter_chain import (
    FilterChainManager,
    generate_filter_chain,
    serialize_value,
)
from audioforge.app.state import create_default_state


def test_generated_stereo_chain_has_safe_order_and_limiter_ceiling():
    state = create_default_state("Club")
    state.output_gain_db = 3.5
    state.limiter_ceiling_db = -1.25

    config = generate_filter_chain(state, sink_name="alsa_output.pci-00_1f.3.analog-stereo")

    names = [module["name"] for module in config["chain"]]
    assert names == ["preamp", "eq", "compressor", "saturation", "imaging", "limiter", "output"]
    assert config["chain"][-2]["parameters"]["ceiling_db"] == -1.25
    assert config["chain"][-1]["parameters"]["gain_db"] == 3.5
    assert config["properties"]["target.object"] == "alsa_output.pci-00_1f.3.analog-stereo"


def test_multichannel_chain_does_not_apply_stereo_imaging():
    state = create_default_state("Cinema")
    state.channel_layout = "5.1"

    config = generate_filter_chain(state, sink_name="surround-sink")

    imaging = next(module for module in config["chain"] if module["name"] == "imaging")
    assert imaging["enabled"] is False
    assert imaging["parameters"]["mode"] == "channel-safe"
    assert config["channel_layout"] == "5.1"


def test_device_names_are_data_not_shell_fragments():
    state = create_default_state()
    sink = 'speaker; touch /tmp/pwned $(echo bad)'

    config = generate_filter_chain(state, sink_name=sink)

    assert config["properties"]["target.object"] == sink
    assert "touch" not in json.dumps(config["chain"])
    assert serialize_value(sink) == json.dumps(sink)


def test_serialization_rejects_non_finite_and_unsupported_values():
    with pytest.raises(ValueError):
        serialize_value(float("nan"))
    with pytest.raises(TypeError):
        serialize_value(object())


def test_manager_writes_config_and_stop_restores_direct_route(tmp_path: Path):
    state = create_default_state()
    calls = []
    manager = FilterChainManager(tmp_path, command_runner=lambda argv: calls.append(argv))

    path = manager.start(state, sink_name="default")
    assert path.exists()
    assert json.loads(path.read_text())["chain"][0]["name"] == "preamp"
    assert manager.mode == "simulation"

    manager.stop()
    assert manager.mode == "direct-fallback"
    assert calls == []
    assert not path.exists()


def test_manager_uses_supported_engine_without_shell_interpolation(tmp_path: Path):
    state = create_default_state()
    calls = []
    manager = FilterChainManager(
        tmp_path,
        command_runner=lambda argv: calls.append(list(argv)) or subprocess.CompletedProcess(argv, 0, "id: 42, type: PipeWire:Interface:Node\n", ""),
        engine_supported=True,
    )

    manager.start(state, sink_name="safe sink")
    node_id = manager.node_id
    manager.stop()

    assert calls[0][0] == "pw-cli"
    assert all(isinstance(arg, str) for arg in calls[0])
    assert "safe sink" not in " ".join(calls[0])
    assert node_id == "42"
    assert calls[-1] == ["pw-cli", "destroy", node_id]


@pytest.mark.parametrize(
    "result",
    [
        subprocess.CompletedProcess([], 0, "", "unknown factory name libpipewire-module-filter-chain"),
        subprocess.CompletedProcess([], 0, "", "warning: creation failed"),
        subprocess.CompletedProcess([], 0, "not an object id", ""),
        subprocess.CompletedProcess([], 1, "id: 42", "creation failed"),
    ],
)
def test_creation_uncertainty_keeps_fallback_and_does_not_destroy(tmp_path: Path, result):
    calls = []

    def runner(argv):
        calls.append(list(argv))
        return result

    manager = FilterChainManager(tmp_path, command_runner=runner, engine_supported=True)
    manager.start(create_default_state())

    assert manager.mode == "fallback"
    assert manager.node_id is None
    manager.stop()
    assert not any(argv[1] == "destroy" for argv in calls)


def test_created_id_must_be_verified_in_graph_before_live(tmp_path: Path):
    calls = []

    def runner(argv):
        calls.append(list(argv))
        if argv[1] == "create-node":
            return subprocess.CompletedProcess(argv, 0, "id: 42, type: PipeWire:Interface:Node\n", "")
        return subprocess.CompletedProcess(argv, 1, "", "object not found")

    manager = FilterChainManager(tmp_path, command_runner=runner, engine_supported=True)
    manager.start(create_default_state())

    assert manager.mode == "fallback"
    assert manager.node_id is None
    assert calls[-1] == ["pw-cli", "info", "42"]
