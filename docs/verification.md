# AudioForge verification

Verification was run from `/home/minhhuynh/audioforge`.

## Exact commands

```bash
PYTHONPATH=. uv run --with pytest pytest -q
python3 -m compileall -q audioforge
node --check audioforge/ui/app.js
PYTHONPATH=. python3 audioforge/scripts/audioforge-pw-check.py
```

Launch, HTTP/UI asset, and SIGTERM cleanup smoke:

```bash
PYTHONPATH=. python3 audioforge/scripts/audioforge.py --port 18766 --config-dir "$TMPDIR/audioforge-smoke-config"
# while running, request /api/state, /, and /styles.css; then send SIGTERM
```

The automated launch smoke asserted HTTP readiness, the `AUDIOFORGE` UI marker, the `focus-visible` CSS rule, clean SIGTERM exit (`0`), and an empty temporary config directory after shutdown.

## Results

- Full suite: **66 passed, 1 skipped** in the current run (`PYTHONPATH=. uv run --with pytest pytest -q`).
- New end-to-end smoke coverage includes Chill switching, Chill preset restore, and Chill A/B snapshot restoration alongside safe startup, Club/Cinema switching, isolated A/B snapshots, bypass/mute, missing PipeWire, and preset round-trip/listing.
- Compileall: passed.
- JavaScript syntax check: passed (`node --check audioforge/ui/app.js`).
- Launch/HTTP/UI/SIGTERM smoke: passed; no filter-chain config remained in the temporary config directory.

## Host PipeWire result

The read-only diagnostic found:

- PipeWire discovery: available
- Default sink: `alsa_output.pci-0000_00_1f.3.hdmi-stereo`
- Sample rate: `48000`
- Channels: `2`
- Layout: `stereo`
- Native path: exercised by `audioforge/scripts/native-pipewire-smoke.py` when run explicitly

The API reports `live` only after the child process and virtual sink graph are verified. Otherwise it retains bypass and reports simulation or fallback.

The Chill defaults currently render as: bass **+1.5 dB @ 90 Hz shelf**, low **+1.0 dB @ 220 Hz**, mid **+1.5 dB @ 1.2 kHz**, presence **-0.5 dB @ 3.2 kHz**, air **-0.5 dB @ 9 kHz**, compressor **-24.0 dB / 1.6:1**, saturation **0.03**, width **1.08**, limiter **-2.0 dB**.

## Known limitations

- Native graph verification requires the host PipeWire tools and a working filter-chain module.
- Simulation meters are deterministic analyzer output, not proof of system-wide realtime processing.
- Stereo is the primary supported chain; multichannel film processing and explicit downmix behavior remain future work.
- Routing is limited to the discovered default sink; per-application routing is not implemented.
- The UI is local-only and does not provide authentication for any externally exposed proxy.
