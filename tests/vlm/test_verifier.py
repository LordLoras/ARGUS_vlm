from __future__ import annotations

import json
from unittest.mock import patch

import httpx
import pytest

from ad_classifier.vlm.models import VLMVerificationResult
from ad_classifier.vlm.verifier import (
    HTTPVLMVerifier,
    MockVLMVerifier,
    _extract_json,
    _normalize_chat_endpoint,
    _parse_vlm_content,
    _vlm_response_format,
)

# ---------------------------------------------------------------------------
# _extract_json
# ---------------------------------------------------------------------------


def test_extract_json_plain():
    raw = '{"primary_category": "other", "confidence": 0.5}'
    assert json.loads(_extract_json(raw)) == {"primary_category": "other", "confidence": 0.5}


def test_extract_json_fenced():
    raw = '```json\n{"primary_category": "other"}\n```'
    assert json.loads(_extract_json(raw)) == {"primary_category": "other"}


def test_extract_json_with_preamble():
    raw = 'Here is the result:\n{"primary_category": "other", "confidence": 0.4}'
    result = json.loads(_extract_json(raw))
    assert result["primary_category"] == "other"


# ---------------------------------------------------------------------------
# MockVLMVerifier
# ---------------------------------------------------------------------------


def _make_bundle():
    from ad_classifier.ingest.models import WhisperTranscript
    from ad_classifier.pipeline.evidence.models import EvidenceBundle

    return EvidenceBundle(
        ad_id="ad_test",
        frame_summaries=[],
        frame_image_paths=[],
        full_transcript=WhisperTranscript(segments=[], text=""),
        rules_triggered=[],
        metadata={},
    )


def test_mock_verifier_returns_default_result():
    verifier = MockVLMVerifier()
    bundle = _make_bundle()
    result = verifier.verify(bundle)
    assert isinstance(result, VLMVerificationResult)
    assert result.primary_category == "other"
    assert result.parse_ok is True


def test_mock_verifier_returns_custom_result():
    custom = VLMVerificationResult(
        primary_category="gambling",
        confidence=0.9,
        summary="high risk gambling ad",
    )
    verifier = MockVLMVerifier(result=custom)
    bundle = _make_bundle()
    result = verifier.verify(bundle)
    assert result.primary_category == "gambling"


# ---------------------------------------------------------------------------
# VLMVerificationResult.parse_failure
# ---------------------------------------------------------------------------


def test_parse_failure_factory():
    result = VLMVerificationResult.parse_failure("raw response here", "invalid JSON")
    assert result.parse_ok is False
    assert result.raw_response == "raw response here"
    assert "invalid JSON" in result.parse_error


# ---------------------------------------------------------------------------
# HTTPVLMVerifier (mocked chat_completion)
# ---------------------------------------------------------------------------


def _mock_chat_data(payload: dict, finish_reason: str = "stop"):
    return {
        "choices": [
            {
                "index": 0,
                "message": {"content": json.dumps(payload), "role": "assistant"},
                "finish_reason": finish_reason,
            }
        ]
    }


def _make_http_verifier(**overrides):
    kwargs = {
        "endpoint": "http://mock/v1/chat/completions",
        "model": "test-vlm",
        "temperature": 0.1,
        "max_tokens": 4096,
        "stream": False,
    }
    kwargs.update(overrides)
    return HTTPVLMVerifier(**kwargs)


def test_normalize_chat_endpoint_accepts_base_v1_url():
    assert (
        _normalize_chat_endpoint("http://127.0.0.1:1234/v1/")
        == "http://127.0.0.1:1234/v1/chat/completions"
    )
    assert (
        _normalize_chat_endpoint("http://127.0.0.1:1234/v1/chat/completions")
        == "http://127.0.0.1:1234/v1/chat/completions"
    )


def test_http_verifier_happy_path():
    payload = {
        "primary_category": "retail_ecommerce",
        "confidence": 0.85,
        "summary": "clean ad",
    }
    bundle = _make_bundle()
    with patch("ad_classifier.vlm.verifier.chat_completion", return_value=_mock_chat_data(payload)):
        verifier = _make_http_verifier()
        result = verifier.verify(bundle)
    assert result.primary_category == "retail_ecommerce"
    assert result.confidence == pytest.approx(0.85)
    assert result.parse_ok is True


def test_http_verifier_requests_structured_output():
    payload = {
        "primary_category": "retail_ecommerce",
        "confidence": 0.85,
        "summary": "clean ad",
    }
    bundle = _make_bundle()
    with patch(
        "ad_classifier.vlm.verifier.chat_completion", return_value=_mock_chat_data(payload)
    ) as mock_cc:
        verifier = _make_http_verifier()
        verifier.verify(bundle)

    call_kwargs = mock_cc.call_args.kwargs
    assert call_kwargs["json"]["model"] == "test-vlm"
    assert call_kwargs["json"]["temperature"] == 0.1
    assert call_kwargs["json"]["max_tokens"] == 4096
    assert call_kwargs["json"]["response_format"]["type"] == "json_object"


def test_vlm_response_format_returns_json_object():
    fmt = _vlm_response_format()
    assert fmt["type"] == "json_object"


def test_http_verifier_reads_reasoning_content_when_content_empty():
    payload = {
        "primary_category": "other",
        "confidence": 0.7,
        "summary": "reasoning field only",
    }
    data = {
        "choices": [
            {
                "index": 0,
                "message": {
                    "content": "",
                    "reasoning_content": json.dumps(payload),
                    "role": "assistant",
                },
                "finish_reason": "stop",
            }
        ]
    }
    bundle = _make_bundle()
    with patch("ad_classifier.vlm.verifier.chat_completion", return_value=data):
        verifier = _make_http_verifier()
        result = verifier.verify(bundle)
    assert result.parse_ok is True
    assert result.summary == "reasoning field only"


def test_http_verifier_includes_error_body_on_http_failure():
    request = httpx.Request("POST", "http://mock/v1/chat/completions")
    response = httpx.Response(400, request=request, text="Channel Error")
    bundle = _make_bundle()
    with patch(
        "ad_classifier.vlm.verifier.chat_completion",
        side_effect=httpx.HTTPStatusError("400", request=request, response=response),
    ):
        verifier = _make_http_verifier(endpoint="http://mock/v1", max_retries=0)
        result = verifier.verify(bundle)
    assert result.parse_ok is False
    assert "Channel Error" in result.parse_error


def test_http_verifier_parses_fenced_json():
    payload = {
        "primary_category": "other",
        "confidence": 0.5,
        "summary": "fenced",
    }
    fenced_content = f"```json\n{json.dumps(payload)}\n```"
    data = {
        "choices": [
            {
                "index": 0,
                "message": {"content": fenced_content, "role": "assistant"},
                "finish_reason": "stop",
            }
        ]
    }
    bundle = _make_bundle()
    with patch("ad_classifier.vlm.verifier.chat_completion", return_value=data):
        verifier = _make_http_verifier()
        result = verifier.verify(bundle)
    assert result.primary_category == "other"


def test_http_verifier_ignores_unknown_fields():
    payload = {
        "primary_category": "other",
        "confidence": 0.5,
        "summary": "ok",
        "unknown_future_field": "some value",
    }
    bundle = _make_bundle()
    with patch("ad_classifier.vlm.verifier.chat_completion", return_value=_mock_chat_data(payload)):
        verifier = _make_http_verifier()
        result = verifier.verify(bundle)
    assert result.summary == "ok"


def test_http_verifier_uses_generation_settings_from_constructor():
    payload = {
        "primary_category": "other",
        "confidence": 0.8,
        "summary": "ok",
    }
    bundle = _make_bundle()
    with patch(
        "ad_classifier.vlm.verifier.chat_completion", return_value=_mock_chat_data(payload)
    ) as mock_cc:
        verifier = _make_http_verifier(
            model="qwen-test-model",
            temperature=0.0,
            max_tokens=2048,
        )
        verifier.verify(bundle)

    call_kwargs = mock_cc.call_args.kwargs
    assert call_kwargs["json"]["model"] == "qwen-test-model"
    assert call_kwargs["json"]["temperature"] == 0.0
    assert call_kwargs["json"]["max_tokens"] == 2048


def test_parse_vlm_content_salvages_malformed_nested_json():
    raw = (
        '{"primary_category":"automotive","confidence":0.95,'
        '"evidence":[{"time_ms":11000,"frame_index":22,"source":"ocr",'
        '"text":"0% APR financing","confidence":0.95}],'
        '"marketing_entities":{"brand":{"name":"Jeep","logo_present":true,'
        '"logo_evidence":[],"tagline":"There is only one"},'
        '"products":["2025 Grand Cherokee"],'
        '"offers":[{"type":"flat_off","value":"$4,500 bonus cash"}],'
        '"contact_points":{"websites":[{"url":"string","domain":"Twin Cities Jeep",'
        '"display_text":"twincitiesjeep.com","evidence":[]}]},'
        '"offer_terms":{"expiry":{"text":"Must take retail delivery","evidence":['
        '{"time_ms":11000,"text":"Must take retail delivery","reason":"\\", '
        '\\"confidence\\": 0.0}] } BROKEN,'
        '"creative_attributes":{"format":"brand_spot","disclaimer_density":"medium"},'
        '"campaign_suggestions":[{"name":"Declaration of Deals","confidence":0.9,"evidence":[]}]},'
        '"summary":"usable summary"}'
    )

    result = _parse_vlm_content(raw)

    assert result.parse_ok is False
    assert result.primary_category == "automotive"
    assert result.confidence == pytest.approx(0.95)
    assert result.evidence[0].text == "0% APR financing"
    assert result.marketing_entities.brand.name == "Jeep"
    assert result.marketing_entities.products == ["2025 Grand Cherokee"]
    assert result.marketing_entities.offers[0].value == "$4,500 bonus cash"
    assert result.marketing_entities.contact_points.websites[0].url == "https://twincitiesjeep.com"
    assert result.marketing_entities.contact_points.websites[0].domain == "twincitiesjeep.com"
    assert result.marketing_entities.creative_attributes.format == "brand_spot"
    assert result.marketing_entities.campaign_suggestions[0].name == "Declaration of Deals"
