from __future__ import annotations

from ad_classifier.diagnostics.env import check_torch


def test_torch_diagnostic_imports_without_requiring_gpu():
    info = check_torch(require_gpu=False)

    assert info.version
    assert info.backend in {"CUDA/ROCm", "DirectML", "CPU"}
    assert isinstance(info.gpu_available, bool)
