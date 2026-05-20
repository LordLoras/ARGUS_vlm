from ad_classifier.pipeline.paddlevl.gating import should_run_paddlevl
from ad_classifier.pipeline.paddlevl.models import PaddleVLGatingConfig, PaddleVLOutput

_PARSER_EXPORTS = {
    "DocumentParser",
    "GLMOCRParser",
    "MockPaddleVLParser",
    "PaddleVLParser",
}

__all__ = [
    "PaddleVLGatingConfig",
    "PaddleVLOutput",
    "DocumentParser",
    "GLMOCRParser",
    "MockPaddleVLParser",
    "PaddleVLParser",
    "should_run_paddlevl",
]


def __getattr__(name: str):
    if name in _PARSER_EXPORTS:
        from importlib import import_module

        module = import_module("ad_classifier.pipeline.paddlevl.parser")
        return getattr(module, name)
    raise AttributeError(name)
