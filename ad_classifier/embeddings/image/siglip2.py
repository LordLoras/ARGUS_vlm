from __future__ import annotations

from pathlib import Path

from ad_classifier.embeddings.dependencies import embedding_import_error
from ad_classifier.embeddings.image.base import ImageEmbedder


class SigLIP2ImageEmbedder(ImageEmbedder):
    """SigLIP 2 embedder for image vectors and cross-modal text queries."""

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
                raise embedding_import_error(
                    display_name="SigLIP 2 image embeddings",
                    root_modules={"torch", "transformers"},
                    exc=exc,
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
            if hasattr(model, "get_image_features"):
                pooled = model.get_image_features(pixel_values=inputs["pixel_values"])
            else:
                outputs = model.vision_model(pixel_values=inputs["pixel_values"])
                pooled = outputs.pooler_output  # (B, 768)

        return pooled.cpu().numpy().tolist()

    def embed_text(self, text: str) -> list[float]:
        return self.embed_text_batch([text])[0]

    def embed_text_batch(self, texts: list[str]) -> list[list[float]]:
        processor, model = self._load()
        torch = self._torch

        inputs = processor(text=texts, return_tensors="pt", padding=True, truncation=True)
        inputs = {k: v.to(self._device) for k, v in inputs.items()}

        with torch.no_grad():
            if hasattr(model, "get_text_features"):
                pooled = model.get_text_features(**inputs)
            else:
                outputs = model.text_model(**inputs)
                pooled = outputs.pooler_output  # (B, 768)

        return pooled.cpu().numpy().tolist()
