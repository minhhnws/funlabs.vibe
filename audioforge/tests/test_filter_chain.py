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
    manager = FilterChainManager(tmp_path)

    path = manager.start(state, sink_name="default")
    assert path.exists()
    assert json.loads(path.read_text())["chain"][0]["name"] == "preamp"
    assert manager.mode == "simulation"

    manager.stop()
    assert manager.mode == "direct-fallback"
    assert not path.exists()


class FakeAdapter:
    def __init__(self, create, verify=None):
        self.create_result = create
        self.verify_result = verify
        self.calls = []

    def create(self, path: Path):
        self.calls.append(("create", path))
        return self.create_result

    def verify(self, node_id: str):
        self.calls.append(("verify", node_id))
        return self.verify_result

    def destroy(self, node_id: str):
        self.calls.append(("destroy", node_id))
        return subprocess.CompletedProcess([], 0, "", "")


def test_live_requires_explicit_validated_adapter(tmp_path: Path):
    state = create_default_state()
    manager = FilterChainManager(
        tmp_path,
        engine_supported=True,
    )

    manager.start(state, sink_name="safe sink")
    assert manager.mode == "simulation"
    manager.stop()

    assert manager.mode == "direct-fallback"
    assert manager.node_id is None


def test_validated_adapter_must_verify_before_live(tmp_path: Path):
    adapter = FakeAdapter(
        subprocess.CompletedProcess([], 0, "id: 42, type: PipeWire:Interface:Node\n", ""),
        subprocess.CompletedProcess([], 0, "id: 42, type: PipeWire:Interface:Node\n", ""),
    )
    manager = FilterChainManager(tmp_path, adapter=adapter)
    manager.start(create_default_state(), sink_name="safe sink")
    manager.stop()
    assert manager.mode == "direct-fallback"
    assert [kind for kind, _ in adapter.calls] == ["create", "verify", "destroy"]


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
    adapter = FakeAdapter(result)
    manager = FilterChainManager(tmp_path, adapter=adapter)
    manager.start(create_default_state())

    assert manager.mode == "fallback"
    assert manager.node_id is None
    manager.stop()
    assert not any(kind == "destroy" for kind, _ in adapter.calls)


def test_created_id_must_be_verified_in_graph_before_live(tmp_path: Path):
    adapter = FakeAdapter(
        subprocess.CompletedProcess([], 0, "id: 42, type: PipeWire:Interface:Node\n", ""),
        subprocess.CompletedProcess([], 1, "", "object not found"),
    )
    manager = FilterChainManager(tmp_path, adapter=adapter)
    manager.start(create_default_state())

    assert manager.mode == "fallback"
    assert manager.node_id is None
    assert [kind for kind, _ in adapter.calls] == ["create", "verify"]
    assert not any(kind == "destroy" for kind, _ in adapter.calls)
    assert not list(tmp_path.iterdir())
