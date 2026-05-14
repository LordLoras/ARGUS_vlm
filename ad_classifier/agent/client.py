from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import Any

import httpx

from ad_classifier._env import resolve_api_key
from ad_classifier.agent.models import ToolCall
from ad_classifier.vlm.http import chat_completion


class AgentClientError(RuntimeError):
    pass


class AgentClient(ABC):
    """Abstract LM Studio / OpenAI-compatible chat completion client."""

    @abstractmethod
    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AgentMessage: ...


class AgentMessage:
    """Lightweight wrapper for the model's response, mirroring OpenAI shape."""

    def __init__(
        self,
        *,
        content: str | None,
        tool_calls: list[ToolCall],
        finish_reason: str | None = None,
        raw: dict[str, Any] | None = None,
    ) -> None:
        self.content = content
        self.tool_calls = tool_calls
        self.finish_reason = finish_reason
        self.raw = raw or {}


def _normalize_chat_endpoint(endpoint: str) -> str:
    normalized = endpoint.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    if normalized.endswith("/v1"):
        return f"{normalized}/chat/completions"
    return f"{normalized}/v1/chat/completions"


def _coerce_args(raw: Any) -> dict[str, Any]:
    if raw is None or raw == "":
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {"_raw": raw}
        return parsed if isinstance(parsed, dict) else {"_value": parsed}
    return {"_raw": str(raw)}


def parse_tool_calls(message: dict[str, Any]) -> list[ToolCall]:
    raw_calls = message.get("tool_calls") or []
    out: list[ToolCall] = []
    for i, raw in enumerate(raw_calls):
        function = raw.get("function") or {}
        name = function.get("name")
        if not name:
            continue
        out.append(
            ToolCall(
                id=str(raw.get("id") or f"call_{i}"),
                name=str(name),
                arguments=_coerce_args(function.get("arguments")),
            )
        )
    return out


class HTTPAgentClient(AgentClient):
    def __init__(
        self,
        *,
        endpoint: str = "http://127.0.0.1:1234/v1",
        model: str = "argus/vlm",
        api_key_env: str | None = None,
        timeout_s: float = 120.0,
        max_retries: int = 2,
        retry_delay_s: float = 2.0,
        temperature: float = 0.1,
        max_tokens: int = 1024,
        stream: bool = True,
    ) -> None:
        self._endpoint = _normalize_chat_endpoint(endpoint)
        self._model = model
        self._timeout_s = timeout_s
        self._max_retries = max_retries
        self._retry_delay_s = retry_delay_s
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._stream = stream

        api_key = resolve_api_key(api_key_env)
        self._headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AgentMessage:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        last_error: str = "no attempts made"
        for attempt in range(self._max_retries + 1):
            if attempt > 0:
                time.sleep(self._retry_delay_s)
            try:
                data = chat_completion(
                    endpoint=self._endpoint,
                    headers=self._headers,
                    json=payload,
                    timeout_s=self._timeout_s,
                    stream=self._stream,
                )
                choice = (data.get("choices") or [{}])[0]
                message = choice.get("message") or {}
                return AgentMessage(
                    content=message.get("content"),
                    tool_calls=parse_tool_calls(message),
                    finish_reason=choice.get("finish_reason"),
                    raw=data,
                )
            except httpx.HTTPStatusError as exc:
                body = exc.response.text[:500] if exc.response is not None else ""
                status = exc.response.status_code if exc.response is not None else "unknown"
                last_error = f"HTTP {status}: {body!r}"
            except httpx.RequestError as exc:
                last_error = f"request error: {exc}"

        raise AgentClientError(last_error)


class MockAgentClient(AgentClient):
    """Replays a scripted sequence of model responses; used by tests + offline CLI."""

    def __init__(self, responses: Iterable[AgentMessage]) -> None:
        self._responses = list(responses)
        self._index = 0
        self.calls: list[dict[str, Any]] = []

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AgentMessage:
        self.calls.append({"messages": list(messages), "tools": list(tools or [])})
        if self._index >= len(self._responses):
            raise AgentClientError("MockAgentClient exhausted")
        response = self._responses[self._index]
        self._index += 1
        return response
