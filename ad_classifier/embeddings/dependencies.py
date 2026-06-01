from __future__ import annotations

EMBEDDING_INSTALL_COMMANDS = (
    "python -m pip install --no-deps "
    "sentence-transformers==3.0.1 transformers==4.57.6 tokenizers==0.22.1\n"
    "python -m pip install huggingface-hub==0.36.2 "
    "regex==2026.5.9 safetensors==0.7.0 scikit-learn==1.8.0"
)


def embedding_import_error(
    *,
    display_name: str,
    root_modules: set[str],
    exc: ImportError,
    needs_torch: bool = True,
) -> ImportError:
    missing = getattr(exc, "name", None)
    if missing == "torch" and needs_torch:
        message = (
            "torch is missing from the active environment. Install the correct "
            "NVIDIA, AMD, or CPU torch wheel first, then run:\n"
            f"{EMBEDDING_INSTALL_COMMANDS}"
        )
    elif missing and missing not in root_modules:
        message = (
            f"{display_name} is installed, but dependency '{missing}' is missing "
            "from the active environment. Run from the same venv:\n"
            f"{EMBEDDING_INSTALL_COMMANDS}"
        )
    else:
        message = (
            f"{display_name} is not installed in the active environment. "
            "Run from the same venv:\n"
            f"{EMBEDDING_INSTALL_COMMANDS}"
        )
    return ImportError(message)
