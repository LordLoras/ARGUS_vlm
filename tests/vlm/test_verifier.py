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
        verifier = HTTPVLMVerifier(endpoint="http://mock/v1/chat/completions")
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
        verifier = HTTPVLMVerifier(endpoint="http://mock/v1/chat/completions")
        verifier.verify(bundle)

    request_payload = post.call_args.kwargs["json"]
    assert request_payload["response_format"]["type"] == "json_schema"
    assert (
        request_payload["response_format"]["json_schema"]["name"]
        == _vlm_response_format()["json_schema"]["name"]
    )


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
        verifier = HTTPVLMVerifier()
        result = verifier.verify(bundle)
    assert result.parse_ok is True
    assert result.summary == "reasoning field only"


def test_http_verifier_includes_error_body_on_http_failure():
    request = httpx.Request("POST", "http://mock/v1/chat/completions")
    response = httpx.Response(400, request=request, text="Channel Error")
    bundle = _make_bundle()
    with patch("httpx.post", return_value=response):
        verifier = HTTPVLMVerifier(endpoint="http://mock/v1", max_retries=0)
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
        verifier = HTTPVLMVerifier()
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
        verifier = HTTPVLMVerifier()
        result = verifier.verify(bundle)
    assert result.decision == "allow"
