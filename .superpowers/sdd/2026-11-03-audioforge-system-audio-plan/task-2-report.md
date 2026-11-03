# Task 2 report — PipeWire discovery, routing status, and safe fallback

## Outcome

Implemented the Task 2 PipeWire discovery and safe engine lifecycle. Discovery is read-only and isolated behind an injected subprocess runner, so unit tests never mutate the host graph. Engine startup begins bypassed and only enables processing after a valid default sink and channel layout are discovered. Missing commands, malformed/unavailable graphs, and device-loss-like discovery failures route the state to a direct fallback with a visible reason.

## Files created

- `audioforge/app/pipewire.py`
  - `PipeWireAdapter` with injectable runner and subprocess boundary.
  - `SinkInfo` and `ChannelLayout` status models.
  - `discover_default_sink()` parses `pw-dump`, default metadata, sink identity, sample rate, and channel count.
  - `discover_channel_layout()` handles stereo, 5.1, and generic multichannel metadata.
  - Explicit `available`, `unavailable`, and `fallback` discovery states.
- `audioforge/app/engine.py`
  - `EngineStatus` lifecycle/status model.
  - `start_engine()`, `stop_engine()`, `set_bypass()`, and `safe_fallback()`.
  - Validated state is applied before startup; failures always preserve bypass and use direct fallback.
  - Stereo reports documented `downmix_required`; multichannel disables stereo widening.
- `audioforge/tests/test_pipewire.py`
  - Valid dump, missing `pw-dump`, disappearing sink, stereo, and 5.1 coverage.
- `audioforge/tests/test_engine.py`
  - Safe startup, fallback, multichannel behavior, bypass/stop, and fallback reporting coverage.
- `audioforge/scripts/audioforge-pw-check.py`
  - Read-only diagnostic showing availability, sink, sample rate, channels, layout, and filter-chain availability.

## Verification

- Focused tests: `10 passed`
- Full existing and Task 2 suite: `20 passed`
- Compile check: `python3 -m compileall -q audioforge`
- Diagnostic on current host:
  - PipeWire available: yes
  - Default sink: `alsa_output.pci-0000_00_1f.3.hdmi-stereo`
  - Sample rate: `48000`
  - Channels/layout: `2` / `stereo`
  - Real filter-chain path: unavailable (discovery only)
- `git diff --check`: clean

## Known limitations

- Task 2 provides discovery and lifecycle status only; it does not create or own a real filter-chain. The diagnostic reports this truthfully.
- The current implementation treats a stereo output as requiring the documented downmix stage before stereo processing; no actual audio conversion is performed until the later filter-chain task.

## Fix round 1 — review findings

- Stereo layout discovery and engine status now keep `stereo_widening` disabled; the regression test asserts the corrected behavior.
- Layout resolution verifies that the sink is still present in the second snapshot and returns an explicit `fallback` status if it disappeared, preventing stale sink metadata from being reported as available.
- `subprocess.CalledProcessError` is handled by direct discovery and layout discovery. Non-zero `pw-dump` exits now return visible `unavailable`/fallback statuses with stderr diagnostics instead of propagating tracebacks.
- Added regression tests for stereo widening, mid-resolution sink disappearance, and non-zero `pw-dump` exits.

### Fix verification

- Focused suite: `14 passed` via `PYTHONPATH=. uv run --with pytest pytest audioforge/tests/test_pipewire.py audioforge/tests/test_engine.py -q`.
- Full suite: `24 passed` via `PYTHONPATH=. uv run --with pytest pytest -q`.
- Compile check: `uv run --with pytest python -m compileall -q audioforge`.
- Diagnostic: `audioforge-pw-check.py` exited `0`; PipeWire available, default sink `alsa_output.pci-0000_00_1f.3.hdmi-stereo`, 48000 Hz stereo; filter-chain path unavailable (discovery only).
