from ad_classifier.embeddings.dependencies import embedding_import_error
from ad_classifier.embeddings.image.base import ImageEmbedder
from ad_classifier.embeddings.image.mock import MockImageEmbedder

__all__ = ["ImageEmbedder", "MockImageEmbedder", "SigLIP2ImageEmbedder"]


def SigLIP2ImageEmbedder(*args, **kwargs):
    try:
        from ad_classifier.embeddings.image.siglip2 import SigLIP2ImageEmbedder as _SigLIP2
        return _SigLIP2(*args, **kwargs)
    except ImportError as exc:
        raise embedding_import_error(
            display_name="SigLIP 2 image embeddings",
            root_modules={"torch", "transformers"},
            exc=exc,
        ) from exc
