# Task 3 report — Local API and DJ/Cinema UI

## Outcome

Implemented the localhost-only AudioForge JSON control surface and a polished dark DJ/Cinema control UI. The server consumes the existing `AudioState`, analyzer, presets, PipeWire discovery, and engine lifecycle interfaces; it does not duplicate DSP/business state models.

## API

Created `audioforge/app/server.py` with:

- `GET /api/state` — versioned serialized state, analyzer frame, and engine status.
- `GET /api/presets` — local preset names.
- `POST /api/state` — validated bounded state/module mutation.
- `POST /api/profile` — Club/Cinema profile switching.
- `POST /api/snapshot` — A/B snapshot storage.
- `POST /api/action` — module enable, gain, EQ, dynamics, width, bypass, mute, A/B comparison, loudness matching, preset save/load, and reset-to-safe actions.
- `GET /api/events` — one-shot SSE status and analyzer events suitable for polling/reconnect clients.
- Structured JSON validation errors with HTTP 400.
- Localhost-only bind enforcement and localhost-only CORS.
- Explicit `SIMULATION / PipeWire unavailable`, `FALLBACK / Direct output`, and live status mapping. The current engine only provides discovery/lifecycle, not a real filter chain, so the API reports simulation rather than claiming live DSP.

## UI

Created:

- `audioforge/ui/index.html`
- `audioforge/ui/styles.css`
- `audioforge/ui/app.js`

The UI includes graphite styling, Club/Cinema profile accents, chain module rail, realtime analyzer canvas, waveform, stereo meters, loudness/true-peak cards, output device/routing status, gain/width/loudness controls, bypass/mute, A/B snapshots, preset actions, and reset-to-safe. All required action names have client handlers, and simulation status is rendered distinctly.

## Tests and verification

- Created `audioforge/tests/test_server.py` with state retrieval, bounded mutation, profile switching, A/B snapshots, mute/bypass, validation errors, event stream, and CORS coverage.
- Focused server tests: **3 passed**.
- Full suite: **27 passed**.
- Compile check: `uv run --with pytest python -m compileall -q audioforge` passed.
- Static UI smoke check passed: HTML asset references, required controls/actions, simulation label, and key layout sections confirmed.
- `git diff --check` passed.

## Limitations

- Task 2 exposes PipeWire discovery/lifecycle only and explicitly does not own a real filter-chain; UI/API therefore remain truthful simulation/fallback rather than claiming real processing.
- The SSE endpoint emits a current status/analyzer snapshot and closes; clients can reconnect for updates.
