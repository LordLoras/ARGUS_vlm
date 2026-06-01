from __future__ import annotations

from ad_classifier.embeddings.dependencies import embedding_import_error


def test_embedding_import_error_names_missing_transitive_dependency():
    original = ModuleNotFoundError("No module named 'huggingface_hub'")
    original.name = "huggingface_hub"

    err = embedding_import_error(
        display_name="sentence-transformers",
        root_modules={"sentence_transformers"},
        exc=original,
    )

    message = str(err)
    assert "dependency 'huggingface_hub' is missing" in message
    assert "scikit-learn" in message
    assert "sentence-transformers==3.0.1" in message


def test_embedding_import_error_keeps_torch_separate():
    original = ModuleNotFoundError("No module named 'torch'")
    original.name = "torch"

    err = embedding_import_error(
        display_name="SigLIP 2 image embeddings",
        root_modules={"torch", "transformers"},
        exc=original,
    )

    message = str(err)
    assert "torch is missing" in message
    assert "Install the correct NVIDIA, AMD, or CPU torch wheel first" in message
