from ad_classifier.embeddings.image.base import ImageEmbedder
from ad_classifier.embeddings.image.mock import MockImageEmbedder

__all__ = ["ImageEmbedder", "MockImageEmbedder", "SigLIP2ImageEmbedder"]


def SigLIP2ImageEmbedder(*args, **kwargs):
    try:
        from ad_classifier.embeddings.image.siglip2 import SigLIP2ImageEmbedder as _SigLIP2
        return _SigLIP2(*args, **kwargs)
    except ImportError as exc:
        raise ImportError(
            "SigLIP 2 image embedder requires torch and transformers. "
            "Install with: pip install --no-deps sentence-transformers transformers tokenizers\n"
            "Or disable visual embeddings in config: image_embedder.enabled = false"
        ) from exc
