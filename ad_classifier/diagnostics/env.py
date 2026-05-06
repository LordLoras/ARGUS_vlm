"""Startup environment check — verifies GPU torch is intact.

Called early in the worker and API entrypoints.
Fails loudly if torch is CPU-only when a GPU build was expected.
"""

from __future__ import annotations

import sys
from typing import NamedTuple


class TorchInfo(NamedTuple):
    version: str
    backend: str
    gpu_available: bool


def check_torch(require_gpu: bool = True) -> TorchInfo:
    try:
        import torch  # noqa: PLC0415
    except ImportError:
        print("ERROR: torch is not installed in this environment.", file=sys.stderr)
        sys.exit(1)

    version = torch.__version__

    if torch.cuda.is_available():
        backend = "CUDA/ROCm"
        gpu_available = True
    elif hasattr(torch, "directml"):
        backend = "DirectML"
        gpu_available = True
    else:
        backend = "CPU"
        gpu_available = False

    print(f"torch {version}  backend={backend}  gpu={gpu_available}")

    if require_gpu and not gpu_available:
        print(
            "ERROR: torch is running CPU-only. "
            "The pre-installed GPU wheel (ROCm/DirectML) appears to have been replaced. "
            "Do NOT run `pip install torch` or `pip install -U torch`. "
            "Re-install the GPU wheel manually.",
            file=sys.stderr,
        )
        sys.exit(1)

    return TorchInfo(version=version, backend=backend, gpu_available=gpu_available)


if __name__ == "__main__":
    info = check_torch(require_gpu=False)
    print(f"version={info.version}  backend={info.backend}  gpu={info.gpu_available}")
