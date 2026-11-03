# AudioForge

AudioForge is a localhost control surface for a PipeWire playback processor. It starts safe: if a real filter-chain node cannot be created, the API remains available but reports `SIMULATION / PipeWire unavailable` or `FALLBACK / Direct output`, and bypass stays enabled.

## Prerequisites

- Linux with Python 3.11+ and `uv` (or a compatible Python environment)
- `pw-dump` for read-only sink/channel discovery
- `pipewire`, `wpctl`, and `pactl` for native system-wide routing
- `curl` for the launch readiness check; an installed desktop opener is optional

Run from the checkout:

```bash
PYTHONPATH=. uv run --with pytest pytest -q
./audioforge/scripts/audioforge-ui.sh
```

The UI is served by the existing local API/UI assets. Open `http://127.0.0.1:8765/` if the browser does not open automatically. `audioforge-pw-check.py` is a read-only diagnostic and explicitly reports that filter-chain integration is unavailable unless the engine is enabled.

## Modes and safety

- **Simulation:** `--disable-native` or `AUDIOFORGE_NATIVE=0` keeps the JSON inspection path and bypass enabled.
- **Live:** the launcher writes a native PipeWire factory `.conf`, starts an owned `pipewire -c` child, verifies the virtual sink graph, makes it default, and moves existing sink-inputs to it.
- **Fallback:** missing tools, invalid graph verification, or failed routing keeps bypass enabled and reports `FALLBACK / Direct output`.
- **Stop:** Ctrl-C or termination moves tracked sink-inputs back, restores the captured original default sink, terminates only the owned child, and removes only the owned `.conf`. Never kill the session PipeWire or WirePlumber process.

The generated order is fixed: preamp → EQ → compressor → saturation → imaging → limiter → output gain. The limiter is always enabled and its ceiling is clamped to the validated safe range. Device names are data fields, not shell fragments.

## Chill profile

**Chill** is the relaxed listening profile: controlled/deeper bass without club loudness, a warm low-mid lift, smooth highs, light compression, moderate stereo width, and a conservative -2.0 dB limiter ceiling. It is a first-class profile across the API, presets/A-B snapshots, UI selector/status, and native PipeWire renderer.

## Native verification

Run the opt-in smoke; it restores routing in `finally`:

```bash
PYTHONPATH=. python3 audioforge/scripts/native-pipewire-smoke.py
```

## Current limits

Stereo is the primary chain. Imaging is disabled for layouts such as 5.1 and marked `channel-safe`; it is not applied across unrelated film channels. A future multichannel implementation must add explicit per-channel processing/downmix behavior before enabling it. This milestone does not promise live-instrument latency or per-application routing.

## Local development

```bash
PYTHONPATH=. uv run --with pytest pytest audioforge/tests/test_filter_chain.py -q
PYTHONPATH=. uv run --with pytest pytest -q
python3 -m compileall -q audioforge
```

The local API binds only to localhost. Do not expose it through a proxy without adding authentication and an explicit safety review.
