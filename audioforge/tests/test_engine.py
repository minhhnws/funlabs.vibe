from audioforge.app.engine import EngineStatus, safe_fallback, set_bypass, start_engine, stop_engine
from audioforge.app.pipewire import PipeWireAdapter
from audioforge.app.state import create_default_state
from audioforge.tests.test_pipewire import dump_payload


def test_start_stays_bypassed_until_discovery_succeeds():
    state = create_default_state()
    adapter = PipeWireAdapter(runner=lambda _argv: dump_payload())
    status = start_engine(state, adapter)
    assert status.mode == "live"
    assert state.bypass is False
    assert status.channel_layout == "stereo"
    assert status.downmix_required is True
    assert status.stereo_widening is True


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
