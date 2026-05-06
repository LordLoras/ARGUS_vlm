from ad_classifier.diagnostics.paddle_rocm import (
    DiagnosticRow,
    diagnostic_explanation,
    format_diagnostic_table,
)


def test_format_diagnostic_table() -> None:
    table = format_diagnostic_table(
        [
            DiagnosticRow("paddle_import_ok", True, "ok"),
            DiagnosticRow("compiled_with_rocm", False, "False"),
        ]
    )

    assert "paddle_import_ok" in table
    assert "compiled_with_rocm" in table
    assert "fail" in table


def test_diagnostic_explanation_for_cpu_paddle() -> None:
    explanation = diagnostic_explanation(
        [
            DiagnosticRow("paddle_import_ok", True, "ok"),
            DiagnosticRow("compiled_with_rocm", False, "False"),
        ]
    )

    assert "CPU-only" in explanation
    assert "acceptable" in explanation
