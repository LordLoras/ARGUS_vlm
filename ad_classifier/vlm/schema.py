from copy import deepcopy
from typing import Any

from ad_classifier.vlm.models import VLMVerificationResult

_PARSING_METADATA_FIELDS = {"parse_ok", "raw_response", "parse_error"}


def _strip_parsing_metadata(schema: dict[str, Any]) -> None:
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return

    for field in _PARSING_METADATA_FIELDS:
        properties.pop(field, None)

    required = schema.get("required")
    if isinstance(required, list):
        schema["required"] = [field for field in required if field not in _PARSING_METADATA_FIELDS]


def vlm_response_format(fmt: str = "json_object") -> dict[str, Any]:
    if fmt == "json_schema":
        schema = deepcopy(VLMVerificationResult.model_json_schema())
        _strip_parsing_metadata(schema)
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "ad_verification_result",
                "schema": schema,
            },
        }
    return {
        "type": "json_object",
    }
