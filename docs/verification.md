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

- Full suite: **54 passed** in 7.99s (`PYTHONPATH=. uv run --with pytest pytest -q`).
- New end-to-end smoke coverage: **6 tests** in `audioforge/tests/test_smoke.py` covering safe startup, Club/Cinema switching, isolated A/B snapshots, bypass/mute, missing PipeWire, and preset round-trip/listing.
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
- Real filter-chain path: unavailable (discovery only)

Accordingly, AudioForge reports simulation/unavailable and retains `bypass=true`; discovery availability is not treated as proof of a validated processing node.

## Known limitations

- The native PipeWire filter-chain adapter is not implemented. No real processing node is created or claimed.
- Simulation meters are deterministic analyzer output, not proof of system-wide realtime processing.
- Stereo is the primary supported chain; multichannel film processing and explicit downmix behavior remain future work.
- Routing is limited to the discovered default sink; per-application routing is not implemented.
- The UI is local-only and does not provide authentication for any externally exposed proxy.
