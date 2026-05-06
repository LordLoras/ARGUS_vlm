from __future__ import annotations

import json
import subprocess
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path

from ad_classifier.pipeline.ocr.models import FrameRef
from ad_classifier.pipeline.paddlevl.models import PaddleVLOutput


class DocumentParser(ABC):
    @abstractmethod
    def parse(self, frame: FrameRef) -> PaddleVLOutput:
        """Run PaddleOCR-VL on a frame and return structured output."""


class MockPaddleVLParser(DocumentParser):
    """Returns a fixed PaddleVLOutput for use in tests."""

    def __init__(
        self,
        *,
        parsed: dict | None = None,
        raw_text: str | None = None,
        parse_ok: bool = True,
    ) -> None:
        self._parsed = parsed or {}
        self._raw_text = raw_text or json.dumps(self._parsed)
        self._parse_ok = parse_ok

    def parse(self, frame: FrameRef) -> PaddleVLOutput:
        return PaddleVLOutput(
            frame_index=frame.frame_index,
            time_ms=frame.time_ms,
            raw_text=self._raw_text,
            parsed=self._parsed if self._parse_ok else None,
            parse_ok=self._parse_ok,
            engine="mock_paddlevl",
        )


class PaddleVLParser(DocumentParser):
    """
    Shell adapter for PaddleX PaddleOCR-VL pipeline.

    Runs only when gating rules request it.  Captures stdout/stderr; parses
    JSON from stdout when available.  Fails gracefully so the pipeline can
    continue with PaddleOCR-only evidence.

    Command template variables: ``{image_path}``, ``{output_dir}``.
    """

    def __init__(
        self,
        command_template: str = (
            "paddlex --pipeline PaddleOCR-VL-native.yaml"
            " --input {image_path} --output {output_dir}"
        ),
        timeout_s: float = 60.0,
    ) -> None:
        self._command_template = command_template
        self._timeout_s = timeout_s

    def parse(self, frame: FrameRef) -> PaddleVLOutput:
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd = self._command_template.format(
                image_path=str(frame.path),
                output_dir=tmpdir,
            )
            try:
                proc = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=self._timeout_s,
                )
            except subprocess.TimeoutExpired:
                return PaddleVLOutput(
                    frame_index=frame.frame_index,
                    time_ms=frame.time_ms,
                    parse_ok=False,
                    stderr=f"timeout after {self._timeout_s}s",
                )
            except Exception as exc:
                return PaddleVLOutput(
                    frame_index=frame.frame_index,
                    time_ms=frame.time_ms,
                    parse_ok=False,
                    stderr=str(exc),
                )

            raw = proc.stdout.strip() or None
            parsed: dict | None = None
            parse_ok = False

            if raw:
                try:
                    data = json.loads(raw)
                    if isinstance(data, dict):
                        parsed = data
                        parse_ok = True
                    else:
                        # Try to find JSON in output dir
                        output_files = list(Path(tmpdir).glob("*.json"))
                        if output_files:
                            data = json.loads(output_files[0].read_text(encoding="utf-8"))
                            if isinstance(data, dict):
                                parsed = data
                                parse_ok = True
                except (json.JSONDecodeError, OSError):
                    pass

            return PaddleVLOutput(
                frame_index=frame.frame_index,
                time_ms=frame.time_ms,
                raw_text=raw,
                parsed=parsed,
                parse_ok=parse_ok,
                stderr=proc.stderr.strip() or None,
            )
