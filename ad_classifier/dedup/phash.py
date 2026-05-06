from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


def image_phash(path: Path) -> str:
    import imagehash  # noqa: PLC0415

    with Image.open(path) as image:
        return str(imagehash.phash(image.convert("RGB")))


def mean_phash(frame_paths: list[Path]) -> str | None:
    import imagehash  # noqa: PLC0415

    if not frame_paths:
        return None

    hash_arrays = []
    for path in frame_paths:
        with Image.open(path) as image:
            hash_arrays.append(
                np.asarray(imagehash.phash(image.convert("RGB")).hash, dtype=np.uint8)
            )

    bit_counts = np.sum(np.stack(hash_arrays, axis=0), axis=0)
    mean_bits = bit_counts >= (len(hash_arrays) / 2)
    return str(imagehash.ImageHash(mean_bits))


def hamming_distance(left: str, right: str) -> int:
    if len(left) != len(right):
        raise ValueError("Cannot compare perceptual hashes with different lengths")
    return sum(
        bin(int(left_digit, 16) ^ int(right_digit, 16)).count("1")
        for left_digit, right_digit in zip(left.lower(), right.lower(), strict=True)
    )
