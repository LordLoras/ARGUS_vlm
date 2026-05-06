from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from ad_classifier.ingest.models import IngestFrame
from ad_classifier.pipeline.preprocess import PreprocessConfig, PreprocessResult, preprocess_frames
from ad_classifier.pipeline.preprocess.analysis import (
    compute_blank_std,
    compute_blur_score,
    compute_pixel_diff,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _checkerboard(path, size=64, square=8):
    """Save a sharp black-and-white checkerboard."""
    arr = np.zeros((size, size, 3), dtype=np.uint8)
    for y in range(size):
        for x in range(size):
            if ((x // square) + (y // square)) % 2 == 0:
                arr[y, x] = 255
    Image.fromarray(arr).save(path)


def _solid(path, color=(255, 255, 255), size=64):
    Image.new("RGB", (size, size), color=color).save(path)


def _frame(frame_index: int, time_ms: int, path) -> IngestFrame:
    return IngestFrame(frame_index=frame_index, time_ms=time_ms, path=path)


# ---------------------------------------------------------------------------
# Unit tests for analysis functions
# ---------------------------------------------------------------------------


def test_blank_std_solid_is_zero(tmp_path):
    p = tmp_path / "white.png"
    _solid(p, color=(255, 255, 255))
    assert compute_blank_std(p) == pytest.approx(0.0)


def test_blank_std_checkerboard_is_high(tmp_path):
    p = tmp_path / "board.png"
    _checkerboard(p)
    assert compute_blank_std(p) > 50.0


def test_blur_score_solid_is_zero(tmp_path):
    p = tmp_path / "white.png"
    _solid(p, color=(200, 200, 200))
    assert compute_blur_score(p) == pytest.approx(0.0, abs=1e-3)


def test_blur_score_checkerboard_is_high(tmp_path):
    p = tmp_path / "board.png"
    _checkerboard(p)
    assert compute_blur_score(p) > 100.0


def test_pixel_diff_identical_is_zero(tmp_path):
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    _solid(a, color=(100, 150, 200))
    _solid(b, color=(100, 150, 200))
    assert compute_pixel_diff(a, b) == pytest.approx(0.0, abs=1e-4)


def test_pixel_diff_opposite_colors_is_high(tmp_path):
    a = tmp_path / "black.png"
    b = tmp_path / "white.png"
    _solid(a, color=(0, 0, 0))
    _solid(b, color=(255, 255, 255))
    assert compute_pixel_diff(a, b) > 0.9


# ---------------------------------------------------------------------------
# Integration tests for preprocess_frames
# ---------------------------------------------------------------------------


def test_empty_input_returns_empty_result():
    result = preprocess_frames([])
    assert isinstance(result, PreprocessResult)
    assert result.frames == []
    assert result.kept_frames == []


def test_single_frame_always_kept(tmp_path):
    p = tmp_path / "frame_0.png"
    _solid(p)  # solid white — would normally be blank
    config = PreprocessConfig(blank_std_threshold=5.0)

    result = preprocess_frames([_frame(0, 0, p)], config)

    assert len(result.frames) == 1
    assert result.frames[0].kept is True


def test_first_and_last_kept_even_when_blank(tmp_path):
    """First and last frames are always retained regardless of quality signals."""
    blank_a = tmp_path / "frame_0.png"
    sharp = tmp_path / "frame_1.png"
    blank_b = tmp_path / "frame_2.png"
    _solid(blank_a)
    _checkerboard(sharp)
    _solid(blank_b)

    config = PreprocessConfig(blank_std_threshold=5.0, blur_laplacian_threshold=10.0)
    result = preprocess_frames(
        [_frame(0, 0, blank_a), _frame(1, 500, sharp), _frame(2, 1000, blank_b)],
        config,
    )

    assert result.frames[0].kept is True, "first frame must be kept"
    assert result.frames[2].kept is True, "last frame must be kept"


def test_blank_frame_in_middle_is_dropped(tmp_path):
    sharp_a = tmp_path / "frame_0.png"
    blank = tmp_path / "frame_1.png"
    sharp_b = tmp_path / "frame_2.png"
    _checkerboard(sharp_a)
    _solid(blank)
    _checkerboard(sharp_b)

    config = PreprocessConfig(blank_std_threshold=5.0, blur_laplacian_threshold=10.0)
    result = preprocess_frames(
        [_frame(0, 0, sharp_a), _frame(1, 500, blank), _frame(2, 1000, sharp_b)],
        config,
    )

    assert result.frames[0].kept is True
    assert result.frames[1].kept is False
    assert result.frames[1].drop_reason == "blank"
    assert result.frames[2].kept is True


def test_phash_duplicate_in_middle_is_dropped(tmp_path):
    """Three identical frames: first and last kept, middle dropped as near-duplicate."""
    for i in range(3):
        p = tmp_path / f"frame_{i}.png"
        _checkerboard(p)

    config = PreprocessConfig(
        blank_std_threshold=5.0,
        blur_laplacian_threshold=10.0,
        phash_hamming_threshold=8,
        pixel_diff_threshold=0.05,
    )
    frames = [_frame(i, i * 500, tmp_path / f"frame_{i}.png") for i in range(3)]
    result = preprocess_frames(frames, config)

    assert result.frames[0].kept is True, "first always kept"
    assert result.frames[1].kept is False, "middle dup should be dropped"
    assert result.frames[1].drop_reason is not None
    assert "phash_dup" in result.frames[1].drop_reason
    assert result.frames[2].kept is True, "last always kept"


def test_scene_change_kept(tmp_path):
    """Frames that differ strongly should all be retained."""
    black = tmp_path / "frame_0.png"
    white = tmp_path / "frame_1.png"
    black2 = tmp_path / "frame_2.png"
    _solid(black, color=(0, 0, 0))
    _solid(white, color=(255, 255, 255))
    _solid(black2, color=(5, 5, 5))

    # Use a very low phash threshold so hamming distance alone won't dup-drop,
    # but pixel_diff between black and white is ~1.0 which also prevents it.
    config = PreprocessConfig(
        blank_std_threshold=0.0,  # disable blank detection for this test
        blur_laplacian_threshold=0.0,  # disable blur detection
        phash_hamming_threshold=64,  # very lenient phash threshold
        pixel_diff_threshold=0.01,  # very tight pixel diff threshold
    )
    frames = [
        _frame(0, 0, black),
        _frame(1, 500, white),
        _frame(2, 1000, black2),
    ]
    result = preprocess_frames(frames, config)

    # black→white has pixel_diff ≈ 1.0 >> 0.01, so frame 1 must be kept
    assert result.frames[1].kept is True, "scene change should be retained"


def test_phash_pixel_diff_both_required_for_drop(tmp_path):
    """A frame with similar phash but large pixel diff should NOT be dropped."""
    # frame_0: checkerboard A
    a = tmp_path / "frame_0.png"
    _checkerboard(a, size=64, square=8)

    # frame_1: inverted checkerboard (very different pixels, but same phash distance pattern)
    arr = np.zeros((64, 64, 3), dtype=np.uint8)
    for y in range(64):
        for x in range(64):
            if ((x // 8) + (y // 8)) % 2 != 0:  # inverted
                arr[y, x] = 255
    b = tmp_path / "frame_1.png"
    Image.fromarray(arr).save(b)

    # frame_2: same as frame_0 (exact dup)
    import shutil

    c = tmp_path / "frame_2.png"
    shutil.copy(a, c)

    config = PreprocessConfig(
        blank_std_threshold=0.0,
        blur_laplacian_threshold=0.0,
        phash_hamming_threshold=64,  # accept any phash distance
        pixel_diff_threshold=0.5,    # pixel diff must be < 0.5 to dup-drop
    )
    frames = [_frame(0, 0, a), _frame(1, 500, b), _frame(2, 1000, c)]
    result = preprocess_frames(frames, config)

    # frame_1 (inverted) has pixel_diff ≈ 1.0 vs frame_0 → should be KEPT
    assert result.frames[1].kept is True, "high pixel diff prevents dup-drop"


def test_result_properties(tmp_path):
    sharp = tmp_path / "frame_0.png"
    blank = tmp_path / "frame_1.png"
    sharp2 = tmp_path / "frame_2.png"
    _checkerboard(sharp)
    _solid(blank)
    _checkerboard(sharp2)

    config = PreprocessConfig(blank_std_threshold=5.0, blur_laplacian_threshold=10.0)
    result = preprocess_frames(
        [_frame(0, 0, sharp), _frame(1, 500, blank), _frame(2, 1000, sharp2)],
        config,
    )

    assert len(result.kept_frames) == 2
    assert len(result.dropped_frames) == 1
    assert result.dropped_frames[0].frame_index == 1
