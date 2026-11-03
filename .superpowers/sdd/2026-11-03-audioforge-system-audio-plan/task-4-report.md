# Task 4 report — AudioForge filter-chain integration

## Status

Implemented and committed as `92f550427c8f0fd7c230090e5b4234d65ae88115` (`feat: connect AudioForge to PipeWire filter chain`).

## What changed

- Added `audioforge/app/filter_chain.py`:
  - Structured chain generation with fixed order: preamp, EQ, compressor, saturation, imaging, limiter, output gain.
  - Validated state values and finite/JSON-safe serialization.
  - Limiter ceiling is sourced from validated state and remains enabled.
  - Imaging is disabled and marked `channel-safe` for non-stereo layouts.
  - Sink names remain data values and are never shell-interpolated.
  - `FilterChainManager` writes a local generated config, supports an injected `pw-cli` command boundary, and removes owned state on stop.
- Wired optional chain manager support into `engine.py` and `server.py`; unsupported or unavailable integration remains bypassed and labeled simulation/fallback.
- Added static UI serving at `/`, `/index.html`, `/styles.css`, and `/app.js` so the launch workflow loads the existing UI.
- Added `audioforge/config/filter-chain.conf.template`.
- Added executable launchers:
  - `audioforge/scripts/audioforge.py` — diagnostic, localhost API startup, signal cleanup.
  - `audioforge/scripts/audioforge-ui.sh` — starts the API, waits for readiness, opens the local UI when available, and tears down cleanly.
- Added `README.md` covering prerequisites, modes, safety, teardown, and stereo/multichannel limits.
- Added `audioforge/tests/test_filter_chain.py` with six focused tests.

## Verification

- Focused: `PYTHONPATH=. uv run --with pytest pytest audioforge/tests/test_filter_chain.py -q` → **6 passed**.
- Full: `PYTHONPATH=. uv run --with pytest pytest -q` → **38 passed**.
- Compile: `python3 -m compileall -q audioforge` → **pass**.
- Diagnostic: `audioforge-pw-check.py` found the default sink and stereo layout, and truthfully reported `Real filter-chain path: unavailable (discovery only)`.
- Launch smoke: local API started; `/` returned the AudioForge UI; `/api/state` returned `simulation` with `bypass: true`; a state update round-tripped output gain.
- Stop smoke: process stopped; port 8765 closed; generated chain file was removed.
- `git diff --check` → **pass**.

## Concerns / limits

- The repository has no packaging metadata, so the requested bare `uv run --with pytest ...` form does not put the checkout on `sys.path`; verification used the equivalent `PYTHONPATH=. uv run --with pytest ...` form.
- The host supports PipeWire discovery, but the real filter-chain node path was not enabled during smoke testing. Live mode is opt-in through `AUDIOFORGE_PIPEWIRE_FILTER_CHAIN=1` and should be validated against the installed PipeWire `pw-cli`/filter-chain module before use.
- Multichannel imaging is deliberately disabled; explicit per-channel processing/downmix behavior remains future work.
