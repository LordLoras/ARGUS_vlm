from __future__ import annotations

import json
from typing import Any

import httpx
import structlog

_logger = structlog.get_logger(__name__)


def make_timeout(timeout_s: float) -> httpx.Timeout:
    return httpx.Timeout(
        connect=30.0,
        read=timeout_s,
        write=30.0,
        pool=30.0,
    )


def _accumulate_sse(line_iter) -> dict[str, Any]:
    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    tool_calls_by_index: dict[int, dict[str, Any]] = {}
    finish_reason: str | None = None
    model = ""
    response_id = "chatcmpl-stream"

    for raw_line in line_iter:
        line = (
            raw_line.strip()
            if isinstance(raw_line, str)
            else raw_line.decode("utf-8", errors="replace").strip()
        )
        if not line:
            continue
        if not line.startswith("data:"):
            continue
        data_str = line[5:].lstrip()
        if data_str.strip() == "[DONE]":
            break
        try:
            chunk = json.loads(data_str)
        except json.JSONDecodeError:
            continue

        response_id = chunk.get("id", response_id)
        model = chunk.get("model", model)
        choices = chunk.get("choices")
        if not choices:
            continue
        choice = choices[0]
        delta = choice.get("delta") or {}
        fr = choice.get("finish_reason")
        if fr is not None:
            finish_reason = fr

        if "content" in delta and delta["content"] is not None:
            content_parts.append(delta["content"])
        if "reasoning_content" in delta and delta["reasoning_content"] is not None:
            reasoning_parts.append(delta["reasoning_content"])
        if "tool_calls" in delta:
            for tc_delta in delta["tool_calls"]:
                idx = tc_delta.get("index", 0)
                if idx not in tool_calls_by_index:
                    tool_calls_by_index[idx] = {
                        "id": "",
                        "function": {"name": "", "arguments": ""},
                    }
                tc = tool_calls_by_index[idx]
                if tc_delta.get("id"):
                    tc["id"] = tc_delta["id"]
                func = tc_delta.get("function") or {}
                if func.get("name"):
                    tc["function"]["name"] = func["name"]
                if func.get("arguments"):
                    tc["function"]["arguments"] += func["arguments"]

    message: dict[str, Any] = {}
    message["content"] = "".join(content_parts) if content_parts else None
    message["role"] = "assistant"
    if reasoning_parts:
        message["reasoning_content"] = "".join(reasoning_parts)
    if tool_calls_by_index:
        message["tool_calls"] = [
            {
                "id": tc["id"],
                "type": "function",
                "function": {
                    "name": tc["function"]["name"],
                    "arguments": tc["function"]["arguments"],
                },
            }
            for idx in sorted(tool_calls_by_index)
            for tc in [tool_calls_by_index[idx]]
        ]

    return {
        "id": response_id,
        "object": "chat.completion",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": finish_reason or "stop",
            }
        ],
    }


def chat_completion(
    *,
    endpoint: str,
    headers: dict[str, str],
    json: dict[str, Any],
    timeout_s: float,
    stream: bool = True,
) -> dict[str, Any]:
    timeout = make_timeout(timeout_s)
    request_payload = {**json, "stream": stream}

    if stream:
        _logger.debug(
            "chat_completion_streaming_start",
            endpoint=endpoint,
            model=json.get("model", "?"),
        )
        with (
            httpx.Client(timeout=timeout) as client,
            client.stream("POST", endpoint, headers=headers, json=request_payload) as response,
        ):
            if response.is_error:
                response.read()
                response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if "application/json" in content_type:
                response.read()
                return response.json()
            result = _accumulate_sse(response.iter_lines())
        _logger.debug(
            "chat_completion_streaming_done",
            endpoint=endpoint,
            finish_reason=result.get("choices", [{}])[0].get("finish_reason"),
        )
        return result
    else:
        request_payload["stream"] = False
        resp = httpx.post(endpoint, headers=headers, json=request_payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
