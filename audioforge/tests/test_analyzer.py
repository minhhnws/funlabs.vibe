from audioforge.app.analyzer import Analyzer, AnalyzerFrame, generate_frame
from audioforge.app.state import create_default_state


def test_analyzer_frame_shape_is_deterministic():
    state = create_default_state("Club")
    first = generate_frame(state, frame_index=7)
    second = generate_frame(state, frame_index=7)
    assert isinstance(first, AnalyzerFrame)
    assert first == second
    assert len(first.spectrum) == 32
    assert len(first.waveform_left) == 64
    assert len(first.waveform_right) == 64
    assert -120.0 <= first.true_peak_db <= 0.0


def test_analyzer_counter_is_monotonic():
    analyzer = Analyzer(create_default_state())
    assert analyzer.next_frame().frame_index == 0
    assert analyzer.next_frame().frame_index == 1
