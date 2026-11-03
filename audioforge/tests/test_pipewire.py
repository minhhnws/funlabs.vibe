import json
import subprocess

from audioforge.app.pipewire import PipeWireAdapter, discover_channel_layout, discover_default_sink


def dump_payload(*, channels=2, positions=None, sink_name="alsa_output.pci-1"):
    positions = positions or (["FL", "FR"] if channels == 2 else ["FL", "FR", "RL", "RR", "FC", "LFE"])
    return json.dumps([
        {"id": 42, "type": "PipeWire:Interface:Node", "info": {"props": {
            "media.class": "Audio/Sink", "node.name": sink_name,
            "audio.channels": str(channels), "audio.position": " ".join(positions),
            "audio.rate": "48000",
        }}},
        {"id": 99, "type": "PipeWire:Interface:Metadata", "info": {"props": {
            "metadata.name": "default", "metadata.default.audio.sink": sink_name,
        }}},
    ])


def runner_ok(argv):
    assert argv == ["pw-dump"]
    return dump_payload()


def test_valid_pw_dump_discovers_default_sink_without_host_mutation():
    adapter = PipeWireAdapter(runner=runner_ok)
    sink = discover_default_sink(adapter)
    assert sink.available is True
    assert sink.name == "alsa_output.pci-1"
    assert sink.object_id == 42
    assert adapter.commands == [["pw-dump"]]


def test_missing_pw_dump_is_unavailable():
    def missing(_argv):
        raise FileNotFoundError("pw-dump")

    result = discover_default_sink(PipeWireAdapter(runner=missing))
    assert result.available is False
    assert result.status == "unavailable"
    assert "pw-dump" in result.reason


def test_channel_layout_reads_stereo_metadata():
    adapter = PipeWireAdapter(runner=lambda _argv: dump_payload())
    layout = discover_channel_layout(adapter)
    assert layout.channels == 2
    assert layout.name == "stereo"
    assert layout.downmix_required is True
    assert layout.stereo_widening is False


def test_channel_layout_preserves_5_1_and_disables_stereo_widening():
    adapter = PipeWireAdapter(runner=lambda _argv: dump_payload(channels=6))
    layout = discover_channel_layout(adapter)
    assert layout.channels == 6
    assert layout.name == "5.1"
    assert layout.downmix_required is False
    assert layout.stereo_widening is False


def test_disappearing_sink_reports_fallback():
    adapter = PipeWireAdapter(runner=lambda _argv: json.dumps([]))
    result = discover_default_sink(adapter)
    assert result.available is False
    assert result.status == "fallback"


def test_sink_disappearing_during_layout_resolution_reports_fallback():
    payloads = iter([dump_payload(), json.dumps([])])
    adapter = PipeWireAdapter(runner=lambda _argv: next(payloads))
    result = discover_channel_layout(adapter)
    assert result.available is False
    assert result.status == "fallback"
    assert "disappeared" in result.reason


def test_nonzero_pw_dump_exit_is_unavailable():
    def failed(_argv):
        raise subprocess.CalledProcessError(1, ["pw-dump"], stderr="permission denied")

    result = discover_default_sink(PipeWireAdapter(runner=failed))
    assert result.available is False
    assert result.status == "unavailable"
    assert "permission denied" in result.reason
