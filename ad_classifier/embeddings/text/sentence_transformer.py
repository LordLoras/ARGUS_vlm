from __future__ import annotations

from ad_classifier.embeddings.dependencies import embedding_import_error
from ad_classifier.embeddings.text.base import TextEmbedder


class SentenceTransformerEmbedder(TextEmbedder):
    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        device: str = "cpu",
    ) -> None:
        self._model_name = model_name
        self._device = device
        self._model = None

    def _load(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer  # noqa: PLC0415
            except ImportError as exc:
                raise embedding_import_error(
                    display_name="sentence-transformers",
                    root_modules={"sentence_transformers"},
                    exc=exc,
                ) from exc
            self._model = SentenceTransformer(self._model_name, device=self._device)
        return self._model

    @property
    def dim(self) -> int:
        return self._load().get_sentence_embedding_dimension() or 384

    @property
    def model_name(self) -> str:
        return self._model_name

    def embed(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        model = self._load()
        vectors = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        return [v.tolist() for v in vectors]
