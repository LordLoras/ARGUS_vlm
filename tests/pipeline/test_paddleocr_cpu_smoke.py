from __future__ import annotations

import os

import pytest
from PIL import Image, ImageDraw, ImageFont


@pytest.mark.paddleocr_smoke
def test_paddleocr_cpu_smoke(tmp_path):
    if os.getenv("RUN_PADDLEOCR_SMOKE") != "1":
        pytest.skip("Set RUN_PADDLEOCR_SMOKE=1 to run the PaddleOCR CPU inference smoke test.")

    import paddle  # noqa: PLC0415
    from paddleocr import PaddleOCR  # noqa: PLC0415

    paddle.set_device("cpu")

    image_path = tmp_path / "ocr_smoke.png"
    image = Image.new("RGB", (720, 220), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("arial.ttf", 72)
    except OSError:
        font = ImageFont.load_default()
    draw.text((32, 62), "SALE 50% OFF", fill="black", font=font)
    image.save(image_path)

    ocr = PaddleOCR(use_angle_cls=False, lang="en", use_gpu=False, show_log=False)
    result = ocr.ocr(str(image_path), cls=False)

    text = str(result).upper()
    assert paddle.get_device() == "cpu"
    assert "SALE" in text
