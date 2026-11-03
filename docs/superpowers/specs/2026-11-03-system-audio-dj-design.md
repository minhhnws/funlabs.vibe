# AudioForge — System Audio DJ/Cinema Processor

## Intent

AudioForge is a Linux desktop application that processes all system playback in realtime through PipeWire and presents a professional DJ-style control surface. It is for listening to Deep Drill House/DJ music with controlled punch and loudness, and for watching films with clearer dialogue and spacious sound. It is not a file editor and does not replace the audio driver; it improves the signal before the selected output device.

## Goals

- Capture/play back system audio through a dedicated PipeWire processing path.
- Provide two first-class profiles: **Club** for Deep Drill House/DJ and **Cinema** for films.
- Make the output chain visible and controllable: preamp, parametric EQ, dynamic bass, compressor, gentle saturation, stereo imaging, true-peak limiter, and output gain.
- Provide a polished dark UI with spectrum/waveform visualization, stereo VU meters, gain-reduction meters, large DJ controls, A/B comparison, bypass, undo/redo, preset save/load, and instant mute.
- Keep latency low enough for normal media playback and DJ monitoring, while preventing clipping and unsafe output levels.
- Recover cleanly if processing is disabled or crashes, preserving a usable direct output path.

## Non-goals

- Multitrack recording, waveform cutting, sample editing, or DAW replacement.
- Automatic mastering that silently changes the user's content.
- Driver firmware changes or claims of improving physically limited speakers/headphones.
- Shipping a cloud account, telemetry, or online preset marketplace.

## Anti-goals

- No uncontrolled loudness race: limiter and true-peak protection remain active unless an explicit expert mode is added later.
- No processing that makes Cinema sound like a club mix by default.
- No hidden processing: every active module and major gain change is visible.

## Product shape

A local Linux desktop app, initially built around PipeWire. The UI is a single main workspace with:

1. Top bar: input status, selected output device, sample rate/latency, profile selector, save preset, undo/redo, bypass, and emergency mute.
2. Center: large realtime spectrum with peak hold plus left/right waveform-style energy display.
3. Left chain rail: ordered modules with enable toggles and signal-flow arrows.
4. Main editor: selected module controls. EQ uses draggable frequency bands and numeric controls; dynamics show threshold/ratio/attack/release and gain reduction; imaging shows width and mono compatibility.
5. Right master strip: stereo VU/peak meters, loudness (LUFS), true-peak readout, output gain, limiter reduction, and output device.
6. Bottom transport/status: latency, CPU load, protection state, A/B snapshot, and reset-to-safe controls.

The visual language is dark graphite with restrained amber/cyan accents, high-contrast meters, large touchable knobs, and clear state colors for active/bypassed/protected/clipping.

## Audio behavior

### Club profile

Builder may select sensible starting values, but the default intent is: controlled sub/bass lift, kick/bass separation, moderate bus compression, subtle saturation, moderate stereo width above the low end, and a conservative true-peak ceiling. The chain must avoid pumping and muddy low frequencies.

### Cinema profile

Default intent: mostly transparent EQ, mild dialogue presence support, low-end protection, minimal compression, restrained width, and a conservative limiter. The chain must preserve film dynamics better than Club mode.

### Safety

- Meter true peak and loudness continuously.
- Keep a safe ceiling and expose the ceiling value.
- If clipping or runaway gain is detected, engage protection and show why.
- Mute must cut output immediately and be reversible.
- Bypass must make the processed/direct state obvious.

## Technical direction

Use the existing Linux environment's PipeWire stack rather than a browser-only audio path. The builder may choose the implementation language and DSP library after checking installed toolchains, but should favor maintainable native/local components and a clear separation between DSP state, PipeWire graph integration, and UI state. The first milestone may include a high-fidelity interactive UI with a deterministic simulated signal/analyzer if system integration is unavailable; it must label simulation clearly and keep integration seams ready for real audio.

### Chosen scope defaults

- Stereo is the primary processing model for Club and normal listening.
- When a multichannel film stream and compatible multichannel output are available, preserve its channel layout and apply only channel-safe processing; do not apply stereo widening across unrelated channels.
- When the output is stereo, perform a documented, standard downmix before the stereo chain.
- Process playback routed to the default PipeWire sink by default. Per-application routing is a later extension, not required for the first vertical slice.
- Use a media mode with low practical latency rather than promising live instrument monitoring. The builder should choose a safe buffer/lookahead target and expose the measured latency.
- On engine crash, device loss, or invalid graph state, automatically fall back to the original direct route where possible and visibly report the fallback. Mute only for detected unsafe output until the user acknowledges it.
- A/B means two complete parameter snapshots, with processed-vs-bypassed comparison available separately. A/B and bypass comparisons should offer loudness matching so louder is not mistaken for better.


Presets should be local files with versioned schema. All parameter changes should be undoable and serializable. The app should start in a safe, bypassed state until a valid output path is confirmed.

## Success criteria

A user can select Club or Cinema, see active realtime meters/analyzer, change EQ/dynamics/width/output controls, compare A/B, mute/bypass, and save a preset without ambiguity. With PipeWire available, the app exposes or controls the system playback path; without it, the UI reports the missing prerequisite instead of pretending to process audio.

## Builder decisions left open

- Exact native UI toolkit and language.
- DSP implementation/library and PipeWire graph topology.
- Packaging format and launch integration.
- Initial test/audio-fixture strategy.
- Whether the first vertical slice ships real PipeWire processing or a clearly labeled analyzer/UI spike first.
