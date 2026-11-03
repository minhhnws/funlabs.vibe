from audioforge.app.engine import EngineStatus, safe_fallback, set_bypass, start_engine, stop_engine
from audioforge.app.pipewire import PipeWireAdapter
from audioforge.app.state import create_default_state
from audioforge.tests.test_pipewire import dump_payload


def test_start_stays_bypassed_without_a_filter_chain():
    state = create_default_state()
    adapter = PipeWireAdapter(runner=lambda _argv: dump_payload())
    status = start_engine(state, adapter)
    assert status.mode == "live"
    assert status.filter_chain_available is False
    assert state.bypass is True
    assert status.channel_layout == "stereo"
    assert status.downmix_required is True
    assert status.stereo_widening is False


def test_start_missing_pipewire_calls_safe_fallback():
    state = create_default_state()
    adapter = PipeWireAdapter(runner=lambda _argv: (_ for _ in ()).throw(FileNotFoundError("pw-dump")))
    status = start_engine(state, adapter)
    assert isinstance(status, EngineStatus)
    assert status.mode == "fallback"
    assert state.bypass is True
    assert state.routing == "direct-fallback"
    assert status.reason


def test_multichannel_engine_skips_stereo_widening():
    state = create_default_state()
    adapter = PipeWireAdapter(runner=lambda _argv: dump_payload(channels=6))
    status = start_engine(state, adapter)
    assert status.mode == "live"
    assert status.channel_layout == "5.1"
    assert status.stereo_widening is False
    assert status.downmix_required is False


def test_set_bypass_and_stop_are_safe():
    state = create_default_state()
    adapter = PipeWireAdapter(runner=lambda _argv: dump_payload())
    start_engine(state, adapter)
    set_bypass(state, True)
    assert state.bypass is True
    stopped = stop_engine(state)
    assert stopped.mode == "bypassed"
    assert state.bypass is True


def test_safe_fallback_reports_reason_and_bypasses():
    state = create_default_state()
    status = safe_fallback(state, "sink disappeared")
    assert status.mode == "fallback"
    assert state.bypass is True
    assert state.routing == "direct-fallback"
    assert state.protection == "sink disappeared"


def test_engine_falls_back_if_sink_disappears_during_layout_resolution():
    state = create_default_state()
    payloads = iter([dump_payload(), "[]"])
    adapter = PipeWireAdapter(runner=lambda _argv: next(payloads))
    status = start_engine(state, adapter)
    assert status.mode == "fallback"
    assert state.bypass is True
    assert state.routing == "direct-fallback"
    assert status.reason


def test_engine_reports_nonzero_pw_dump_without_traceback():
    import subprocess

    state = create_default_state()
    def failed(_argv):
        raise subprocess.CalledProcessError(1, ["pw-dump"], stderr="permission denied")

    status = start_engine(state, PipeWireAdapter(runner=failed))
    assert status.mode == "fallback"
    assert state.bypass is True
    assert "permission denied" in status.reason
