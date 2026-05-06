from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DiagnosticRow:
    name: str
    ok: bool
    value: str


def run_paddle_rocm_check(image_path: Path | None = None) -> list[DiagnosticRow]:
    rows: list[DiagnosticRow] = []

    rows.append(_rocm_smi_available())

    try:
        import paddle  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover - depends on optional local install
        rows.append(DiagnosticRow("paddle_import_ok", False, _short_error(exc)))
        rows.extend(
            [
                DiagnosticRow("paddle_version", False, "unavailable"),
                DiagnosticRow("compiled_with_rocm", False, "unavailable"),
                DiagnosticRow("gpu_device_set_ok", False, "paddle import failed"),
                DiagnosticRow("paddle_run_check_ok", False, "paddle import failed"),
            ]
        )
        rows.extend(_paddleocr_checks(image_path, paddle_available=False))
        return rows

    rows.append(DiagnosticRow("paddle_import_ok", True, "ok"))
    rows.append(DiagnosticRow("paddle_version", True, getattr(paddle, "__version__", "unknown")))

    compiled_with_rocm = _bool_call(lambda: paddle.is_compiled_with_rocm())
    rows.append(DiagnosticRow("compiled_with_rocm", compiled_with_rocm, str(compiled_with_rocm)))

    gpu_device_set_ok = False
    try:
        paddle.device.set_device("gpu:0")
        gpu_device_set_ok = True
        value = "gpu:0"
    except Exception as exc:  # pragma: no cover - hardware dependent
        value = _short_error(exc)
    rows.append(DiagnosticRow("gpu_device_set_ok", gpu_device_set_ok, value))

    run_check_ok = False
    try:
        tensor = paddle.ones([2, 2], dtype="float32")
        result = paddle.matmul(tensor, tensor).numpy().tolist()
        run_check_ok = result == [[2.0, 2.0], [2.0, 2.0]]
        value = "matmul ok" if run_check_ok else str(result)
    except Exception as exc:  # pragma: no cover - hardware dependent
        value = _short_error(exc)
    rows.append(DiagnosticRow("paddle_run_check_ok", run_check_ok, value))

    rows.extend(_paddleocr_checks(image_path, paddle_available=True))
    return rows


def format_diagnostic_table(rows: Iterable[DiagnosticRow]) -> str:
    rows = list(rows)
    name_width = max([len("check"), *(len(row.name) for row in rows)])
    status_width = len("status")
    lines = [
        f"{'check'.ljust(name_width)}  {'status'.ljust(status_width)}  value",
        f"{'-' * name_width}  {'-' * status_width}  -----",
    ]
    for row in rows:
        status = "ok" if row.ok else "fail"
        lines.append(f"{row.name.ljust(name_width)}  {status.ljust(status_width)}  {row.value}")
    return "\n".join(lines)


def diagnostic_explanation(rows: Iterable[DiagnosticRow]) -> str:
    by_name = {row.name: row for row in rows}
    if not by_name.get("paddle_import_ok", DiagnosticRow("", False, "")).ok:
        return (
            "PaddlePaddle is not installed or cannot import. Install the CPU wheel for normal use."
        )
    if not by_name.get("compiled_with_rocm", DiagnosticRow("", False, "")).ok:
        return (
            "PaddlePaddle appears to be CPU-only. That is acceptable for this project; "
            "PaddleOCR defaults to CPU on Windows AMD."
        )
    if not by_name.get("gpu_device_set_ok", DiagnosticRow("", False, "")).ok:
        return (
            "The Paddle wheel reports ROCm support but gpu:0 could not be selected. "
            "Check ROCm visibility, GPU support, and the installed Paddle wheel."
        )
    if not by_name.get("paddleocr_inference_ok", DiagnosticRow("", True, "")).ok:
        return (
            "PaddleOCR imported but inference failed. Check PaddleOCR/PaddlePaddle compatibility."
        )
    return "Paddle ROCm diagnostics passed. CPU mode remains the supported default."


def _rocm_smi_available() -> DiagnosticRow:
    import shutil
    import subprocess

    command = shutil.which("rocm-smi") or shutil.which("rocm-smi.exe")
    if command is None:
        return DiagnosticRow("rocm_smi_available", False, "not found on PATH")
    try:
        completed = subprocess.run(
            [command, "--showproductname"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception as exc:  # pragma: no cover - host dependent
        return DiagnosticRow("rocm_smi_available", False, _short_error(exc))
    ok = completed.returncode == 0
    output = (completed.stdout or completed.stderr).strip().splitlines()
    return DiagnosticRow(
        "rocm_smi_available", ok, output[0] if output else str(completed.returncode)
    )


def _paddleocr_checks(image_path: Path | None, *, paddle_available: bool) -> list[DiagnosticRow]:
    try:
        from paddleocr import PaddleOCR  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover - optional dependency
        return [
            DiagnosticRow("paddleocr_import_ok", False, _short_error(exc)),
            DiagnosticRow("paddleocr_inference_ok", False, "paddleocr import failed"),
        ]

    rows = [DiagnosticRow("paddleocr_import_ok", True, "ok")]
    if image_path is None:
        rows.append(DiagnosticRow("paddleocr_inference_ok", True, "skipped: no image supplied"))
        return rows
    if not paddle_available:
        rows.append(DiagnosticRow("paddleocr_inference_ok", False, "paddle import failed"))
        return rows

    try:
        ocr = PaddleOCR(use_angle_cls=False, lang="en", use_gpu=True)
        result = ocr.ocr(str(image_path), cls=False)
        rows.append(
            DiagnosticRow("paddleocr_inference_ok", True, f"{len(result or [])} result groups")
        )
    except Exception as exc:  # pragma: no cover - hardware/model dependent
        rows.append(DiagnosticRow("paddleocr_inference_ok", False, _short_error(exc)))
    return rows


def _bool_call(fn) -> bool:
    try:
        return bool(fn())
    except Exception:
        return False


def _short_error(exc: Exception) -> str:
    text = f"{type(exc).__name__}: {exc}"
    return text if len(text) <= 180 else text[:177] + "..."
