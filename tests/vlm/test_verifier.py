from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

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
    raw = '```json\n{"decision": "allow"}\n```'
    assert json.loads(_extract_json(raw)) == {"decision": "allow"}


def test_extract_json_with_preamble():
    raw = 'Here is the result:\n{"decision": "review", "confidence": 0.4}'
    result = json.loads(_extract_json(raw))
    assert result["decision"] == "review"


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
    assert result.decision == "allow"
    assert result.parse_ok is True


def test_mock_verifier_returns_custom_result():
    custom = VLMVerificationResult(
        primary_category="gambling",
        confidence=0.9,
        decision="flag",
        needs_human_review=True,
        summary="high risk gambling ad",
    )
    verifier = MockVLMVerifier(result=custom)
    bundle = _make_bundle()
    result = verifier.verify(bundle)
    assert result.decision == "flag"
    assert result.primary_category == "gambling"


# ---------------------------------------------------------------------------
# VLMVerificationResult.parse_failure
# ---------------------------------------------------------------------------


def test_parse_failure_factory():
    result = VLMVerificationResult.parse_failure("raw response here", "invalid JSON")
    assert result.parse_ok is False
    assert result.decision == "review"
    assert result.needs_human_review is True
    assert result.raw_response == "raw response here"
    assert "invalid JSON" in result.parse_error


# ---------------------------------------------------------------------------
# HTTPVLMVerifier (mocked httpx)
# ---------------------------------------------------------------------------


def _mock_response(payload: dict, status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = {"choices": [{"message": {"content": json.dumps(payload)}}]}
    resp.raise_for_status = MagicMock()
    return resp


def _make_http_verifier(**overrides):
    kwargs = {
        "endpoint": "http://mock/v1/chat/completions",
        "model": "test-vlm",
        "temperature": 0.1,
        "max_tokens": 4096,
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
        "risk_labels": [],
        "confidence": 0.85,
        "decision": "allow",
        "needs_human_review": False,
        "summary": "clean ad",
    }
    bundle = _make_bundle()
    with patch("httpx.post", return_value=_mock_response(payload)):
        verifier = _make_http_verifier()
        result = verifier.verify(bundle)
    assert result.decision == "allow"
    assert result.primary_category == "retail_ecommerce"
    assert result.confidence == pytest.approx(0.85)
    assert result.parse_ok is True


def test_http_verifier_requests_structured_output():
    payload = {
        "primary_category": "retail_ecommerce",
        "risk_labels": [],
        "confidence": 0.85,
        "decision": "allow",
        "needs_human_review": False,
        "summary": "clean ad",
    }
    bundle = _make_bundle()
    with patch("httpx.post", return_value=_mock_response(payload)) as post:
        verifier = _make_http_verifier()
        verifier.verify(bundle)

    request_payload = post.call_args.kwargs["json"]
    assert request_payload["model"] == "test-vlm"
    assert request_payload["temperature"] == 0.1
    assert request_payload["max_tokens"] == 4096
    assert request_payload["response_format"]["type"] == "json_schema"
    assert (
        request_payload["response_format"]["json_schema"]["name"]
        == _vlm_response_format()["json_schema"]["name"]
    )


def test_vlm_response_format_includes_tracking_fields():
    schema = _vlm_response_format()["json_schema"]["schema"]
    marketing_ref = schema["properties"]["marketing_entities"]["$ref"]
    marketing_key = marketing_ref.removeprefix("#/$defs/")
    marketing_schema = schema["$defs"][marketing_key]

    for field in (
        "contact_points",
        "advertiser",
        "landing_page",
        "offer_terms",
        "creative_attributes",
        "campaign_signals",
    ):
        assert field in marketing_schema["properties"]
        assert field in marketing_schema["required"]


def test_http_verifier_reads_reasoning_content_when_content_empty():
    payload = {
        "primary_category": "other",
        "risk_labels": [],
        "confidence": 0.7,
        "decision": "allow",
        "needs_human_review": False,
        "summary": "reasoning field only",
    }
    resp = MagicMock()
    resp.json.return_value = {
        "choices": [{"message": {"content": "", "reasoning_content": json.dumps(payload)}}]
    }
    resp.raise_for_status = MagicMock()
    bundle = _make_bundle()
    with patch("httpx.post", return_value=resp):
        verifier = _make_http_verifier()
        result = verifier.verify(bundle)
    assert result.parse_ok is True
    assert result.summary == "reasoning field only"


def test_http_verifier_includes_error_body_on_http_failure():
    request = httpx.Request("POST", "http://mock/v1/chat/completions")
    response = httpx.Response(400, request=request, text="Channel Error")
    bundle = _make_bundle()
    with patch("httpx.post", return_value=response):
        verifier = _make_http_verifier(endpoint="http://mock/v1", max_retries=0)
        result = verifier.verify(bundle)
    assert result.parse_ok is False
    assert "Channel Error" in result.parse_error


def test_http_verifier_parses_fenced_json():
    payload = {
        "primary_category": "other",
        "confidence": 0.5,
        "decision": "review",
        "needs_human_review": True,
        "summary": "fenced",
    }
    fenced_content = f"```json\n{json.dumps(payload)}\n```"
    resp = MagicMock()
    resp.json.return_value = {"choices": [{"message": {"content": fenced_content}}]}
    resp.raise_for_status = MagicMock()
    bundle = _make_bundle()
    with patch("httpx.post", return_value=resp):
        verifier = _make_http_verifier()
        result = verifier.verify(bundle)
    assert result.decision == "review"


def test_http_verifier_ignores_unknown_fields():
    payload = {
        "primary_category": "other",
        "confidence": 0.5,
        "decision": "allow",
        "needs_human_review": False,
        "summary": "ok",
        "unknown_future_field": "some value",
    }
    bundle = _make_bundle()
    with patch("httpx.post", return_value=_mock_response(payload)):
        verifier = _make_http_verifier()
        result = verifier.verify(bundle)
    assert result.decision == "allow"


def test_http_verifier_uses_generation_settings_from_constructor():
    payload = {
        "primary_category": "other",
        "risk_labels": [],
        "confidence": 0.8,
        "decision": "allow",
        "needs_human_review": False,
        "summary": "ok",
    }
    bundle = _make_bundle()
    with patch("httpx.post", return_value=_mock_response(payload)) as post:
        verifier = _make_http_verifier(
            model="qwen-test-model",
            temperature=0.0,
            max_tokens=2048,
        )
        verifier.verify(bundle)

    request_payload = post.call_args.kwargs["json"]
    assert request_payload["model"] == "qwen-test-model"
    assert request_payload["temperature"] == 0.0
    assert request_payload["max_tokens"] == 2048


def test_parse_vlm_content_salvages_malformed_nested_json():
    raw = (
        '{"primary_category":"automotive","risk_labels":["rate_disclosure"],'
        '"confidence":0.95,"decision":"allow","needs_human_review":false,'
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
        '"campaign_signals":{"campaign_theme":"Declaration of Deals","evidence":[]}},'
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
    assert result.marketing_entities.campaign_signals.campaign_theme == "Declaration of Deals"
