"""Deterministic simulation analyzer feed."""
from __future__ import annotations

import math
from dataclasses import dataclass

from .state import AudioState


@dataclass(frozen=True)
class AnalyzerFrame:
    frame_index: int
    spectrum: tuple[float, ...]
    waveform_left: tuple[float, ...]
    waveform_right: tuple[float, ...]
    vu_left_db: float
    vu_right_db: float
    loudness_lufs: float
    true_peak_db: float


def generate_frame(state: AudioState, frame_index: int = 0) -> AnalyzerFrame:
    if frame_index < 0:
        raise ValueError("frame_index cannot be negative")
    gain = float(state.output_gain_db)
    profile_bias = 1.5 if state.profile.name == "Club" else 0.0
    spectrum = tuple(round(-48.0 + profile_bias + 18.0 * math.sin((i + 1) * 0.37 + frame_index * 0.11) ** 2, 6) for i in range(32))
    left = tuple(round(0.42 * math.sin((i + frame_index * 3) * 0.21), 6) for i in range(64))
    right = tuple(round(0.42 * math.sin((i + frame_index * 3) * 0.21 + 0.08), 6) for i in range(64))
    # Simulation-only deterministic normalization; measured program loudness
    # is required for realtime matching and is intentionally not claimed.
    vu = -15.0 if state.loudness_match else max(-60.0, min(0.0, -18.0 + profile_bias + gain))
    true_peak = max(-120.0, min(0.0, vu + 3.0))
    return AnalyzerFrame(frame_index, spectrum, left, right, round(vu, 6), round(vu, 6), round(vu - 3.0, 6), round(true_peak, 6))


class Analyzer:
    def __init__(self, state: AudioState):
        self.state = state
        self.frame_index = 0

    def next_frame(self) -> AnalyzerFrame:
        frame = generate_frame(self.state, self.frame_index)
        self.frame_index += 1
        return frame
