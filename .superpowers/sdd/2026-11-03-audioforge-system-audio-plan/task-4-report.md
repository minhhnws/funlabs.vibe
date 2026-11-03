# Task 4 reviewer gate — AudioForge filter-chain integration

## Gate result

- **Spec: FAIL**
- **Quality: FAIL**
- **Fix required: YES, before acceptance**

The generated chain ordering, bounded limiter value, structured serialization, and default safe-bypass behavior are present. The real filter-chain path is not proven safe or available: the opt-in path can report `LIVE / PipeWire` and release bypass without establishing that a PipeWire filter-chain node exists.

## Critical findings

### C1 — Live availability is a false positive and can release the safety bypass

- **File/line:** `audioforge/app/filter_chain.py:279-282`; surfaced by `audioforge/app/engine.py:47-59` and `audioforge/app/server.py:77-90`.
- `pw-cli create-node ...` is invoked with `libpipewire-module-filter-chain` and a config-file path, but the implementation only relies on `subprocess.run(check=True)`. It does not inspect stderr, validate a returned object ID, or query the graph to confirm the node exists. On this host, the exact command returned exit code 0 while stderr reported `unknown factory name libpipewire-module-filter-chain`; the code then fabricated `audioforge-...` as `node_id`, set `mode = "live"`, and the engine would set `state.bypass = False`.
- This violates the required actual-availability claim and fail-safe rule. It is a safety-critical integration defect.
- **Fix required:** use the installed PipeWire filter-chain creation mechanism and valid properties/config format; treat stderr/error responses and missing/invalid object IDs as failure; verify the created node in the graph before setting live/clearing bypass; destroy only a verified owned node.

## Important findings

### I1 — Cleanup is not reliable on direct SIGTERM

- **File/line:** `audioforge/scripts/audioforge.py:36-42`.
- The cleanup is in `finally`, but only `KeyboardInterrupt` is handled. A normal SIGTERM terminates Python without entering this handler path. The shell wrapper sends SIGINT in its own cleanup, but direct use of `audioforge.py` and external termination do not guarantee node destruction, config removal, and direct-route restoration.
- **Fix required:** install signal handlers that initiate orderly shutdown (or otherwise guarantee cleanup for SIGTERM/SIGINT), and test the process-level path.

### I2 — Tests do not prove failed real-node creation remains bypassed

- **File/line:** `audioforge/tests/test_filter_chain.py:669-685`.
- The supported-engine test injects a runner returning `True`; it never exercises a real `pw-cli` failure, stderr-only failure, malformed output, missing object ID, node-verification failure, or the resulting engine/controller status. The shell-safety assertion only proves the sink name is absent from the command because the command does not pass it; it does not prove safe structured handling of the generated target properties.
- **Fix required:** add tests for each failure mode asserting `mode` is fallback/simulation, `filter_chain_available` is false, bypass remains true, no owned node is destroyed as if it existed, and generated state is removed on stop.

### I3 — The claimed real filter-chain configuration is not demonstrated as consumable by PipeWire

- **File/line:** `audioforge/app/filter_chain.py:219-252, 270-280`; `audioforge/config/filter-chain.conf.template:1-17`.
- The generated JSON is an application-shaped chain description, but the launch command passes its path as the second positional argument to `pw-cli create-node`. No adapter translates the ordered modules/parameters into PipeWire filter-chain factory properties, and no test or manual check creates and inspects a real node. The README correctly says live mode is opt-in, but the implementation still claims live based on command completion rather than actual graph state.
- **Fix required:** document and implement the supported PipeWire API/module invocation, or explicitly keep this milestone simulation-only until a real node path is implemented and verified.

## Minor/deferred observations

- `audioforge/app/filter_chain.py:289-299` swallows destroy errors and does not make cleanup/recovery status visible. This is acceptable only after verified ownership and an explicit best-effort cleanup policy; consider reporting residual cleanup failure.
- `audioforge/app/filter_chain.py:283-286` catches a narrow exception set. A command-boundary implementation should normalize runner failures and reset stale `last_error` on success.
- `audioforge/app/server.py:100-106` regenerates the config and tears down/recreates the node on every state update. This is safe only if the real-node lifecycle is transactional; otherwise an update can leave a gap or stale route. Deferred until the real integration path exists.
- `audioforge/scripts/audioforge-ui.sh:18-21` does not fail if readiness is never achieved; it proceeds to browser launch and waits. It should report a startup failure and terminate the child when the readiness deadline expires.
- The prior report stated commit `92f550...`, while the reviewed commit is `1e09d9b...`; correct the provenance if the report is retained.

## Verification performed

- `PYTHONPATH=. uv run --with pytest pytest -q` → **38 passed**.
- `python3 -m compileall -q audioforge` → **pass**.
- `git diff --check 43f6a8f..1e09d9b` → **pass**.
- `pw-cli --help` confirms `create-node <factory-name> [<properties>]`; executing the implementation's command on this host returned exit code 0 but stderr reported `unknown factory name libpipewire-module-filter-chain`, demonstrating why return-code-only detection is unsafe.

Passing unit tests and compilation are insufficient for this gate because the acceptance criteria include actual filter-chain availability, failure recovery, and lifecycle cleanup.

## Fix round 1

- `FilterChainManager` now treats `pw-cli` stderr, nonzero exits, missing/non-numeric object IDs, and graph verification failures as fallback. It only enters live mode after `pw-cli info <id>` confirms the same object ID; only that verified owned ID can be destroyed.
- Added injected-runner regression coverage for the current host's exit-0/stderr-only response (`unknown factory name libpipewire-module-filter-chain`), malformed and missing IDs, nonzero creation, failed graph verification, and engine bypass retention.
- Direct `audioforge.py` installs SIGINT/SIGTERM handlers that enter the existing orderly cleanup path, restoring handlers afterward.
- README now documents the validated-creation and graph-verification gate. The implementation remains truthful simulation/fallback on this host; no live filter-chain node is claimed.

### Fix verification

- `PYTHONPATH=. uv run --with pytest pytest audioforge/tests/test_filter_chain.py audioforge/tests/test_engine.py -q` -> **19 passed**.
- `PYTHONPATH=. uv run --with pytest pytest -q` -> **44 passed**.
- `python3 -m compileall -q audioforge` -> **pass**.
- `PYTHONPATH=. python3 audioforge/scripts/audioforge-pw-check.py` -> PipeWire available; real filter-chain path unavailable (discovery only).
- Launch/stop smoke with HTTP readiness and direct `SIGTERM` -> process exited 0 and generated config was removed.

## Fix round 2

- Removed the unproven native `pw-cli create-node ... <app-json>` path from the production lifecycle. Live mode now requires an explicitly supplied validated adapter implementing create, graph verification, and owned destroy; the normal launcher supplies none and remains simulation/bypassed.
- Creation stderr, nonzero exit, malformed/missing IDs, and graph-verification failures now remove the owned generated config immediately, retain fallback, and never destroy an unverified node. Engine failure-matrix tests assert bypass retention and cleanup; controller coverage continues to assert unavailable chains cannot clear bypass.
- README and the config template now state that the generated JSON is an inspection/simulation artifact, not a PipeWire factory file. The UI launcher now fails and terminates the child if readiness expires.

### Fix round 2 verification

- `PYTHONPATH=. uv run --with pytest pytest audioforge/tests/test_filter_chain.py audioforge/tests/test_engine.py audioforge/tests/test_server.py -q` -> **28 passed**.
- `PYTHONPATH=. uv run --with pytest pytest -q` -> **48 passed**.
- `python3 -m compileall -q audioforge` -> **pass**.
- `PYTHONPATH=. python3 audioforge/scripts/audioforge-pw-check.py` -> PipeWire available; real filter-chain path unavailable (discovery only).
- Direct launch/readiness/HTTP state/SIGTERM smoke -> `mode=simulation`, `bypass=True`, exit code 0, generated config removed.
- `git diff --check` -> **pass**.
