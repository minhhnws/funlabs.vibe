# AudioForge System Audio DJ/Cinema Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local Linux AudioForge app that gives all playback routed to the default PipeWire sink a professional Club/Cinema processing UI, safe realtime controls, and a clear path to real DSP processing.

**Architecture:** A local Python service owns application state, preset files, PipeWire discovery/routing, safety state, and a deterministic analyzer feed. A browser-based local UI provides the dark DJ control surface and communicates with the service over a small versioned HTTP/WebSocket API. The first vertical slice must work as a high-fidelity UI with a clearly labeled simulation mode, then attach to a real PipeWire filter-chain when the host supports the required modules; failures fall back to direct audio and are visible.

**Tech Stack:** Python 3.14 standard library (`http.server`, `asyncio`, `json`, `subprocess`) for the bridge; vanilla HTML/CSS/JS with Canvas/Web Audio-compatible visualization; PipeWire CLI/API integration through `pw-dump`, `pw-cli`, and `pw-link`/filter-chain configuration; pytest for unit tests; no cloud services.

**Spec:** `/home/minhhuynh/audioforge/docs/superpowers/specs/2026-11-03-system-audio-dj-design.md`

## Global Constraints

- "Process playback routed to the default PipeWire sink by default. Per-application routing is a later extension, not required for the first vertical slice."
- "Stereo is the primary processing model for Club and normal listening."
- "When a multichannel film stream and compatible multichannel output are available, preserve its channel layout and apply only channel-safe processing."
- "When the output is stereo, perform a documented, standard downmix before the stereo chain."
- "On engine crash, device loss, or invalid graph state, automatically fall back to the original direct route where possible and visibly report the fallback."
- "A/B means two complete parameter snapshots, with processed-vs-bypassed comparison available separately."
- The app starts safe and bypassed until a valid output path is confirmed.
- No claims of processing when PipeWire integration is unavailable; simulation must be labeled.

## Review Focus

- PipeWire missing or unavailable: startup must show simulation/unavailable state, never claim live processing (Task 2 test).
- Default sink changes or disappears: bridge must report the new route and enter safe fallback (Task 2 test).
- Multichannel metadata: channel-safe mode must avoid stereo widening and expose downmix state (Task 2 test).
- Invalid gain/limiter values: state validation must clamp/reject unsafe values and surface protection (Task 1 test).
- A/B and bypass: snapshot changes must be isolated and loudness-match state must be explicit (Task 1 and Task 3 tests).

---

### Task 1: Core state, presets, safety, and analyzer model

**Files:**
- Create: `audioforge/app/state.py`
- Create: `audioforge/app/presets.py`
- Create: `audioforge/app/analyzer.py`
- Create: `audioforge/tests/test_state.py`
- Create: `audioforge/tests/test_presets.py`
- Create: `audioforge/tests/test_analyzer.py`

**Interfaces:**
- Produces `AudioState`, `ModuleState`, `ProfileState`, `SnapshotState`, `validate_state()`, `save_preset()`, `load_preset()`, and `AnalyzerFrame` for the bridge and UI API.
- `AudioState` includes `profile`, `modules`, `output_gain_db`, `limiter_ceiling_db`, `bypass`, `muted`, `protection`, `routing`, `latency_ms`, `sample_rate`, and `channel_layout`.

- [ ] **Step 1: Write failing tests** for Club/Cinema defaults, bounded gain and limiter values, A/B snapshot isolation, preset round-trip/version rejection, and deterministic analyzer frame shape.
- [ ] **Step 2: Run `pytest audioforge/tests/test_state.py audioforge/tests/test_presets.py audioforge/tests/test_analyzer.py -q`** and verify the tests fail because the modules do not exist.
- [ ] **Step 3: Implement typed state and validation** with explicit safe defaults: bypassed, muted false, limiter enabled, no protection, Club/Cinema module values, and a versioned JSON preset schema.
- [ ] **Step 4: Implement deterministic analyzer generation** from state and a monotonic frame counter so simulation is repeatable and testable.
- [ ] **Step 5: Run the focused tests** and verify PASS.
- [ ] **Step 6: Commit `feat: add safe audio state and preset model`**.

### Task 2: PipeWire discovery, routing status, and safe fallback

**Files:**
- Create: `audioforge/app/pipewire.py`
- Create: `audioforge/app/engine.py`
- Create: `audioforge/tests/test_pipewire.py`
- Create: `audioforge/tests/test_engine.py`
- Create: `audioforge/scripts/audioforge-pw-check.py`

**Interfaces:**
- Consumes `AudioState` and validation from Task 1.
- Produces `PipeWireAdapter`, `EngineStatus`, `discover_default_sink()`, `discover_channel_layout()`, `start_engine()`, `stop_engine()`, `set_bypass()`, and `safe_fallback()`.

- [ ] **Step 1: Write failing tests** using injected command runners for valid `pw-dump`, missing `pw-dump`, disappearing sink, stereo output, and 5.1 metadata; assert no real host mutation occurs in unit tests.
- [ ] **Step 2: Run `pytest audioforge/tests/test_pipewire.py audioforge/tests/test_engine.py -q`** and verify failure at missing adapter/engine symbols.
- [ ] **Step 3: Implement discovery** with a subprocess boundary, JSON parsing, default sink identification, channel layout detection, and explicit `unavailable`/`fallback` statuses.
- [ ] **Step 4: Implement engine lifecycle** so startup is bypassed until discovery succeeds, multichannel skips stereo widening, stereo uses the documented downmix flag, and every failure calls `safe_fallback()`.
- [ ] **Step 5: Implement the diagnostic script** to print PipeWire availability, default sink, sample rate, channels, and whether the real filter-chain path is available.
- [ ] **Step 6: Run focused tests and `python3 audioforge/scripts/audioforge-pw-check.py`**; verify PASS and a truthful host diagnostic.
- [ ] **Step 7: Commit `feat: add PipeWire discovery and fail-safe engine`**.

### Task 3: Local API and UI control surface

**Files:**
- Create: `audioforge/app/server.py`
- Create: `audioforge/ui/index.html`
- Create: `audioforge/ui/styles.css`
- Create: `audioforge/ui/app.js`
- Create: `audioforge/tests/test_server.py`

**Interfaces:**
- Consumes the state/engine interfaces from Tasks 1–2.
- Exposes `GET /api/state`, `GET /api/presets`, `POST /api/state`, `POST /api/profile`, `POST /api/snapshot`, `POST /api/action`, and `GET /api/events`.
- UI actions are `set_module`, `set_gain`, `set_bypass`, `set_mute`, `save_preset`, `load_preset`, `snapshot_a`, `snapshot_b`, `compare_ab`, and `reset_safe`.

- [ ] **Step 1: Write failing API tests** for state retrieval, bounded mutation, profile switching, A/B snapshots, mute/bypass actions, and truthful unavailable/fallback status.
- [ ] **Step 2: Run `pytest audioforge/tests/test_server.py -q`** and verify failure before server implementation.
- [ ] **Step 3: Implement the local server** with JSON-only payloads, versioned state, validation errors, CORS restricted to localhost, and an event stream for analyzer/status updates.
- [ ] **Step 4: Build the UI layout** with dark graphite styling, amber Club/cyan Cinema accents, chain rail, analyzer canvas, master meters, loudness/true-peak cards, output device card, top actions, and bottom latency/protection status.
- [ ] **Step 5: Implement controls** for profile, module enable, EQ band editing, dynamics knobs, width, output gain, bypass, mute, A/B, loudness match, preset save/load, and reset-to-safe.
- [ ] **Step 6: Render simulation status explicitly** as `SIMULATION / PipeWire unavailable` and render real/fallback states distinctly.
- [ ] **Step 7: Run API tests plus a static smoke check** that loads `index.html`, references existing JS/CSS, and confirms all required controls have event handlers.
- [ ] **Step 8: Commit `feat: add AudioForge local API and DJ UI`**.

### Task 4: Real filter-chain integration and launch workflow

**Files:**
- Create: `audioforge/app/filter_chain.py`
- Create: `audioforge/config/filter-chain.conf.template`
- Create: `audioforge/scripts/audioforge.py`
- Create: `audioforge/scripts/audioforge-ui.sh`
- Create: `audioforge/tests/test_filter_chain.py`
- Create: `audioforge/README.md`

**Interfaces:**
- Consumes validated modules and engine status from Tasks 1–3.
- Produces a generated local filter-chain configuration, launch command, and documented teardown/recovery path.

- [ ] **Step 1: Write failing tests** for generated stereo chain ordering, limiter ceiling, multichannel channel-safe behavior, no shell interpolation from device names, and cleanup after stop.
- [ ] **Step 2: Run `pytest audioforge/tests/test_filter_chain.py -q`** and verify failure.
- [ ] **Step 3: Implement config generation** from structured values only; include preamp, EQ, compressor, saturation, channel-safe imaging, limiter, and output gain in the defined order.
- [ ] **Step 4: Connect engine state updates** to the generated chain where supported; on unsupported host/module, keep the UI alive in clearly labeled simulation/fallback mode.
- [ ] **Step 5: Add launch/stop workflow** that starts the local API, opens the UI, runs the diagnostic check, and restores direct routing on exit.
- [ ] **Step 6: Document prerequisites, modes, safety behavior, and current stereo/multichannel limits** in README.
- [ ] **Step 7: Run all tests and a manual local launch check**; verify the UI loads, state changes round-trip, and no unsafe route remains after stop.
- [ ] **Step 8: Commit `feat: connect AudioForge to PipeWire filter chain`**.

### Task 5: End-to-end verification and polish

**Files:**
- Modify: `audioforge/ui/app.js`
- Modify: `audioforge/ui/styles.css`
- Create: `audioforge/tests/test_smoke.py`
- Create: `audioforge/docs/verification.md`

**Interfaces:**
- Consumes the completed local server and engine.
- Produces a repeatable verification report and polished error/protection states.

- [ ] **Step 1: Write smoke tests** covering startup safe state, Club/Cinema switching, A/B compare, bypass/mute, missing PipeWire, and preset persistence.
- [ ] **Step 2: Run the complete suite with `python3 -m pytest -q`** and fix failures without weakening assertions.
- [ ] **Step 3: Exercise the diagnostic and UI manually** with the current host, confirming real PipeWire availability is reported rather than assumed.
- [ ] **Step 4: Polish meter colors, focus states, readable labels, and protection/fallback copy; ensure no control hides whether processing is active.**
- [ ] **Step 5: Write `docs/verification.md`** with exact commands, test count, host PipeWire result, and known limitations.
- [ ] **Step 6: Run the final suite and launch smoke check**; only then report the app as complete.
- [ ] **Step 7: Commit `test: verify AudioForge end to end`**.
