#!/usr/bin/env python3
"""Run the localhost AudioForge API with fail-safe chain teardown."""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from audioforge.app.engine import stop_engine  # noqa: E402
from audioforge.app.filter_chain import FilterChainManager  # noqa: E402
from audioforge.app.native import NativePipeWireHost  # noqa: E402
from audioforge.app.server import AudioForgeController, create_server  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--config-dir", default=str(Path.home() / ".cache" / "audioforge"))
    parser.add_argument("--diagnostic", action="store_true")
    parser.add_argument("--disable-native", action="store_true")
    args = parser.parse_args()

    native = None if args.disable_native or os.environ.get("AUDIOFORGE_NATIVE", "1") == "0" else NativePipeWireHost(args.config_dir)
    manager = FilterChainManager(args.config_dir, adapter=native)
    controller = AudioForgeController(chain_manager=manager)
    if args.diagnostic:
        check = ROOT / "audioforge" / "scripts" / "audioforge-pw-check.py"
        subprocess.run([sys.executable, str(check)], check=False)
    server = create_server(args.host, args.port, controller=controller)
    print(f"AudioForge API listening on http://{args.host}:{args.port}", flush=True)
    def request_shutdown(_signum, _frame):
        raise KeyboardInterrupt

    previous_handlers = {signum: signal.getsignal(signum) for signum in (signal.SIGINT, signal.SIGTERM)}
    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
        stop_engine(controller.state, manager)
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
