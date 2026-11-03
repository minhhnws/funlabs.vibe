#!/usr/bin/env python3
"""Opt-in real PipeWire smoke; always restores the original route."""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from audioforge.app.native import NativePipeWireHost
from audioforge.app.state import create_default_state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default=f"audioforge_smoke_{time.time_ns()}")
    args = parser.parse_args()
    missing = [cmd for cmd in ("pipewire", "pw-dump", "wpctl", "pactl") if shutil.which(cmd) is None]
    if missing:
        print("missing commands: " + ", ".join(missing), file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix="audioforge-native-") as directory:
        host = NativePipeWireHost(directory, sink_name=args.name)
        host.start(create_default_state())
        result = 0
        try:
            if host.mode != "live" or not host.virtual_id:
                print(f"native host failed: {host.last_error}", file=sys.stderr)
                result = 1
            else:
                print(f"live: sink={args.name} object={host.virtual_id}")
        finally:
            host.stop()
            if host.mode != "direct-fallback" or Path(directory, f"{args.name}.conf").exists():
                print("cleanup verification failed", file=sys.stderr)
                result = 1
        return result


if __name__ == "__main__":
    raise SystemExit(main())
