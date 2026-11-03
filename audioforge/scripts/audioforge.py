#!/usr/bin/env python3
"""Run the localhost AudioForge API with fail-safe chain teardown."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from audioforge.app.engine import stop_engine  # noqa: E402
from audioforge.app.filter_chain import FilterChainManager  # noqa: E402
from audioforge.app.server import AudioForgeController, create_server  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--config-dir", default=str(Path.home() / ".cache" / "audioforge"))
    parser.add_argument("--diagnostic", action="store_true")
    args = parser.parse_args()

    if args.diagnostic:
        check = ROOT / "audioforge" / "scripts" / "audioforge-pw-check.py"
        subprocess.run([sys.executable, str(check)], check=False)

    supported = os.environ.get("AUDIOFORGE_PIPEWIRE_FILTER_CHAIN") == "1"
    manager = FilterChainManager(args.config_dir, engine_supported=supported)
    controller = AudioForgeController(chain_manager=manager)
    server = create_server(args.host, args.port, controller=controller)
    print(f"AudioForge API listening on http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop_engine(controller.state, manager)
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
