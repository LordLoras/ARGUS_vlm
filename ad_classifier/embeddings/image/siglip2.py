from __future__ import annotations

from pathlib import Path

from ad_classifier.embeddings.image.base import ImageEmbedder


class SigLIP2ImageEmbedder(ImageEmbedder):
    """Per-frame visual embedder using google/siglip2-base-patch16-224."""

    def __init__(
        self,
        model_name: str = "google/siglip2-base-patch16-224",
        device: str = "cpu",
    ) -> None:
        self._model_name = model_name
        self._device = device
        self._processor = None
        self._model = None

    def _load(self):
        if self._model is None:
            try:
                import torch  # noqa: PLC0415
                from transformers import AutoModel, AutoProcessor  # noqa: PLC0415
            except ImportError as exc:
                raise ImportError(
                    "transformers and torch are required for SigLIP2ImageEmbedder. "
                    "Install with: pip install --no-deps transformers"
                ) from exc
            self._processor = AutoProcessor.from_pretrained(self._model_name, use_fast=True)
            self._model = AutoModel.from_pretrained(self._model_name).to(self._device)
            self._model.eval()
            self._torch = torch
        return self._processor, self._model

    @property
    def dim(self) -> int:
        return 768

    @property
    def model_name(self) -> str:
        return self._model_name

    def embed(self, path: Path) -> list[float]:
        return self.embed_batch([path])[0]

    def embed_batch(self, paths: list[Path]) -> list[list[float]]:
        from PIL import Image  # noqa: PLC0415

        processor, model = self._load()
        torch = self._torch

        images = [Image.open(p).convert("RGB") for p in paths]
        inputs = processor(images=images, return_tensors="pt", padding=True)
        inputs = {k: v.to(self._device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = model.vision_model(pixel_values=inputs["pixel_values"])
            pooled = outputs.pooler_output  # (B, 768)

        return pooled.cpu().numpy().tolist()
