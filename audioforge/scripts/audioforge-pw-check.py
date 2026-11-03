#!/usr/bin/env python3
"""Print a truthful, read-only PipeWire capability check."""
from __future__ import annotations

import sys
from pathlib import Path

# Allow running this file directly from a checkout without installation.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from audioforge.app.native import detect_native_graph  # noqa: E402
from audioforge.app.pipewire import PipeWireAdapter, discover_channel_layout, discover_default_sink  # noqa: E402


def main() -> int:
    adapter = PipeWireAdapter()
    graph = detect_native_graph()
    sink = discover_default_sink(adapter)
    print(f"PipeWire available: {'yes' if sink.available else 'no'}")
    if not sink.available:
        print(f"Status: {sink.status}")
        print(f"Reason: {sink.reason or 'unknown'}")
        print("Real filter-chain path: active" if graph else "Real filter-chain path: unavailable")
        return 1
    layout = discover_channel_layout(adapter)
    print(f"Default sink: {sink.name}")
    print(f"Sample rate: {sink.sample_rate or 'unknown'}")
    print(f"Channels: {layout.channels or sink.channels}")
    print(f"Channel layout: {layout.name}")
    print("Real filter-chain path: active" if graph else "Real filter-chain path: unavailable")
    return 0 if layout.available else 1


if __name__ == "__main__":
    raise SystemExit(main())
