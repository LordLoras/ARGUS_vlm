from __future__ import annotations

from unittest.mock import MagicMock, patch

from ad_classifier.vlm.http import _accumulate_sse, chat_completion, make_timeout


class TestMakeTimeout:
    def test_creates_timeout_with_granular_phases(self):
        t = make_timeout(600.0)
        assert t.connect == 30.0
        assert t.read == 600.0
        assert t.write == 30.0
        assert t.pool == 30.0

    def test_short_timeout(self):
        t = make_timeout(60.0)
        assert t.read == 60.0


class TestAccumulateSSE:
    def test_accumulates_content_deltas(self):
        lines = [
            'data: {"choices":[{"delta":{"content":"Hello"},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{"content":" world"},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
            "data: [DONE]",
        ]
        result = _accumulate_sse(lines)
        assert result["choices"][0]["message"]["content"] == "Hello world"
        assert result["choices"][0]["finish_reason"] == "stop"

    def test_accepts_data_line_without_space(self):
        lines = [
            'data:{"choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}]}',
            "data:[DONE]",
        ]
        result = _accumulate_sse(lines)
        assert result["choices"][0]["message"]["content"] == "ok"

    def test_accumulates_reasoning_content(self):
        lines = [
            'data: {"choices":[{"delta":{"reasoning_content":"thinking..."},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{"content":"answer"},"finish_reason":"stop"}]}',
            "data: [DONE]",
        ]
        result = _accumulate_sse(lines)
        assert result["choices"][0]["message"]["content"] == "answer"
        assert result["choices"][0]["message"]["reasoning_content"] == "thinking..."

    def test_accumulates_tool_calls(self):
        lines = [
            'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_1","function":{"name":"list_ads","arguments":""}}]},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{\\"brand\\":\\"Jeep\\"}"}}]},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}',
            "data: [DONE]",
        ]
        result = _accumulate_sse(lines)
        tc = result["choices"][0]["message"]["tool_calls"]
        assert len(tc) == 1
        assert tc[0]["id"] == "call_1"
        assert tc[0]["function"]["name"] == "list_ads"

    def test_skips_empty_lines_and_non_data_lines(self):
        lines = [
            "",
            ": this is a comment",
            'data: {"choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}]}',
            "data: [DONE]",
        ]
        result = _accumulate_sse(lines)
        assert result["choices"][0]["message"]["content"] == "ok"

    def test_handles_no_choices(self):
        lines = [
            'data: {"model":"test","choices":[]}',
            "data: [DONE]",
        ]
        result = _accumulate_sse(lines)
        assert result["model"] == "test"
        assert result["choices"][0]["message"]["content"] is None

    def test_uses_defaults_when_no_chunks(self):
        result = _accumulate_sse([])
        assert result["choices"][0]["message"]["content"] is None
        assert result["choices"][0]["finish_reason"] == "stop"
        assert result["id"] == "chatcmpl-stream"


class TestChatCompletionNonStreaming:
    def test_non_streaming_sends_stream_false(self):
        payload = {"model": "test", "messages": [{"role": "user", "content": "hi"}]}
        with patch("httpx.post") as mock_post:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "choices": [{"message": {"content": "Hi"}, "finish_reason": "stop"}]
            }
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            result = chat_completion(
                endpoint="http://localhost:1234/v1/chat/completions",
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout_s=120.0,
                stream=False,
            )

            call_kwargs = mock_post.call_args.kwargs
            assert call_kwargs["json"]["stream"] is False
            assert result["choices"][0]["message"]["content"] == "Hi"

    def test_streaming_sends_stream_true_and_uses_client(self):
        payload = {"model": "test", "messages": [{"role": "user", "content": "hi"}]}
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.is_error = False
        mock_response.iter_lines.return_value = iter(
            [
                'data: {"choices":[{"delta":{"content":"Hi"},"finish_reason":null}]}',
                'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
                "data: [DONE]",
            ]
        )

        mock_client.stream.return_value.__enter__ = MagicMock(return_value=mock_response)
        mock_client.stream.return_value.__exit__ = MagicMock(return_value=False)
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        with patch("httpx.Client", return_value=mock_client):
            result = chat_completion(
                endpoint="http://localhost:1234/v1/chat/completions",
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout_s=120.0,
                stream=True,
            )

        assert result["choices"][0]["message"]["content"] == "Hi"

    def test_streaming_falls_back_when_server_returns_json(self):
        payload = {"model": "test", "messages": [{"role": "user", "content": "hi"}]}
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.is_error = False
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "plain json"}, "finish_reason": "stop"}]
        }

        mock_client.stream.return_value.__enter__ = MagicMock(return_value=mock_response)
        mock_client.stream.return_value.__exit__ = MagicMock(return_value=False)
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        with patch("httpx.Client", return_value=mock_client):
            result = chat_completion(
                endpoint="http://localhost:1234/v1/chat/completions",
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout_s=120.0,
                stream=True,
            )

        mock_response.read.assert_called_once()
        assert result["choices"][0]["message"]["content"] == "plain json"
