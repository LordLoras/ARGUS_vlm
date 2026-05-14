from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from ad_classifier.agent.client import (
    AgentClientError,
    HTTPAgentClient,
    _coerce_args,
    _normalize_chat_endpoint,
    parse_tool_calls,
)


def test_normalize_chat_endpoint():
    assert (
        _normalize_chat_endpoint("http://localhost:1234/v1")
        == "http://localhost:1234/v1/chat/completions"
    )
    assert (
        _normalize_chat_endpoint("http://localhost:1234/v1/")
        == "http://localhost:1234/v1/chat/completions"
    )
    assert (
        _normalize_chat_endpoint("http://localhost:1234/v1/chat/completions")
        == "http://localhost:1234/v1/chat/completions"
    )


def test_parse_tool_calls_with_json_string_arguments():
    raw = {
        "tool_calls": [
            {
                "id": "call_a",
                "function": {"name": "list_ads", "arguments": '{"brand": "Jeep"}'},
            }
        ]
    }
    calls = parse_tool_calls(raw)
    assert calls[0].name == "list_ads"
    assert calls[0].arguments == {"brand": "Jeep"}


def test_parse_tool_calls_with_dict_arguments():
    raw = {
        "tool_calls": [
            {
                "id": "call_b",
                "function": {"name": "count_ads", "arguments": {"brand": "Jeep"}},
            }
        ]
    }
    calls = parse_tool_calls(raw)
    assert calls[0].arguments == {"brand": "Jeep"}


def test_coerce_args_handles_invalid_json():
    assert _coerce_args("not json") == {"_raw": "not json"}
    assert _coerce_args(None) == {}
    assert _coerce_args("") == {}


def _mock_chat_data(body: dict):
    return body


def test_http_client_returns_text_message():
    data = {
        "choices": [
            {
                "message": {"content": "Hi", "tool_calls": None},
                "finish_reason": "stop",
            }
        ]
    }
    with patch("ad_classifier.agent.client.chat_completion", return_value=data):
        client = HTTPAgentClient(endpoint="http://mock/v1")
        result = client.complete([{"role": "user", "content": "hi"}])
    assert result.content == "Hi"
    assert result.tool_calls == []


def test_http_client_returns_tool_call():
    data = {
        "choices": [
            {
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "x",
                            "function": {
                                "name": "list_ads",
                                "arguments": '{"limit": 5}',
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ]
    }
    with patch("ad_classifier.agent.client.chat_completion", return_value=data):
        client = HTTPAgentClient(endpoint="http://mock/v1")
        result = client.complete([{"role": "user", "content": "hi"}])
    assert result.tool_calls[0].name == "list_ads"
    assert result.tool_calls[0].arguments == {"limit": 5}


def test_http_client_retries_then_raises():
    request = httpx.Request("POST", "http://mock/v1/chat/completions")
    response = httpx.Response(500, request=request, text="boom")
    with patch(
        "ad_classifier.agent.client.chat_completion",
        side_effect=httpx.HTTPStatusError("500", request=request, response=response),
    ):
        client = HTTPAgentClient(endpoint="http://mock/v1", max_retries=1, retry_delay_s=0)
        with pytest.raises(AgentClientError):
            client.complete([{"role": "user", "content": "hi"}])
