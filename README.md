# AudioForge

AudioForge is a localhost control surface for a PipeWire playback processor. It starts safe: if a real filter-chain node cannot be created, the API remains available but reports `SIMULATION / PipeWire unavailable` or `FALLBACK / Direct output`, and bypass stays enabled.

## Prerequisites

- Linux with Python 3.11+ and `uv` (or a compatible Python environment)
- `pw-dump` for read-only sink/channel discovery
- Optional real integration: PipeWire's filter-chain module and `pw-cli`
- `curl` for the launch readiness check; an installed desktop opener is optional

Run from the checkout:

```bash
PYTHONPATH=. uv run --with pytest pytest -q
./audioforge/scripts/audioforge-ui.sh
```

The UI is served by the existing local API/UI assets. Open `http://127.0.0.1:8765/` if the browser does not open automatically. `audioforge-pw-check.py` is a read-only diagnostic and explicitly reports that filter-chain integration is unavailable unless the engine is enabled.

## Modes and safety

- **Simulation:** structured filter-chain JSON is generated for inspection, but no PipeWire node is claimed or created.
- **Live:** set `AUDIOFORGE_PIPEWIRE_FILTER_CHAIN=1` only after verifying the host's `pw-cli` filter-chain support. The command receives an argument list, never a shell string.
- **Fallback:** missing `pw-dump`, a disappearing sink, an unsupported module, or a failed node command keeps output bypassed and leaves the direct route preferred.
- **Stop:** Ctrl-C or termination destroys the owned node when present, removes the generated config, and restores the direct/bypassed route. Never kill `pipewire` or `wireplumber` as application cleanup.

The generated order is fixed: preamp → EQ → compressor → saturation → imaging → limiter → output gain. The limiter is always enabled and its ceiling is clamped to the validated safe range. Device names are data fields, not shell fragments.

## Current limits

Stereo is the primary chain. Imaging is disabled for layouts such as 5.1 and marked `channel-safe`; it is not applied across unrelated film channels. A future multichannel implementation must add explicit per-channel processing/downmix behavior before enabling it. This milestone does not promise live-instrument latency or per-application routing.

## Local development

```bash
PYTHONPATH=. uv run --with pytest pytest audioforge/tests/test_filter_chain.py -q
PYTHONPATH=. uv run --with pytest pytest -q
python3 -m compileall -q audioforge
```

The local API binds only to localhost. Do not expose it through a proxy without adding authentication and an explicit safety review.
