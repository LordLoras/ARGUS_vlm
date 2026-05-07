from __future__ import annotations

from ad_classifier.agent.catalog import ToolCatalog
from ad_classifier.agent.client import AgentMessage, MockAgentClient
from ad_classifier.agent.loop import AgentLoop, AgentRunContext
from ad_classifier.agent.models import ToolCall
from ad_classifier.config import AgentConfig
from ad_classifier.db.repositories.agent import (
    AgentMessageRepository,
    AgentSessionRepository,
)


def _build_loop(writable_conn, readonly_conn, client, config: AgentConfig | None = None):
    run = AgentRunContext(
        persistence_conn=writable_conn,
        tool_conn=readonly_conn,
        catalog=ToolCatalog(),
        client=client,
        config=config or AgentConfig(),
    )
    return AgentLoop(run)


def test_simple_text_response_finishes(writable_conn, readonly_conn):
    client = MockAgentClient(
        [AgentMessage(content="Hello there.", tool_calls=[], finish_reason="stop")]
    )
    loop = _build_loop(writable_conn, readonly_conn, client)
    answer = loop.ask("hi")
    assert answer.text == "Hello there."
    assert answer.iterations == 1
    assert answer.tool_calls == []
    # Session should be persisted
    sessions = AgentSessionRepository(writable_conn).list()
    assert len(sessions) == 1
    messages = AgentMessageRepository(writable_conn).list_for_session(sessions[0].id)
    assert [m.role for m in messages] == ["user", "assistant"]


def test_tool_call_then_answer(writable_conn, readonly_conn):
    tool_call = ToolCall(id="call_1", name="count_ads", arguments={"brand": "Jeep"})
    client = MockAgentClient(
        [
            AgentMessage(content=None, tool_calls=[tool_call], finish_reason="tool_calls"),
            AgentMessage(
                content="Jeep has 2 ads (ad_jeep_a, ad_jeep_b).",
                tool_calls=[],
                finish_reason="stop",
            ),
        ]
    )
    loop = _build_loop(writable_conn, readonly_conn, client)
    answer = loop.ask("how many Jeep ads?")
    assert answer.iterations == 2
    assert answer.tool_calls[0].name == "count_ads"
    assert answer.tool_results[0].ok is True
    assert answer.tool_results[0].data == {
        "count": 2,
        "filters": {"brand": "Jeep"},
    }
    assert "Jeep" in answer.text

    # Check the messages persisted include the tool turn
    sid = answer.session_id
    rows = AgentMessageRepository(writable_conn).list_for_session(sid)
    roles = [r.role for r in rows]
    assert "tool" in roles
    tool_row = next(r for r in rows if r.role == "tool")
    assert tool_row.tool_name == "count_ads"
    assert tool_row.tool_args_json is not None
    assert tool_row.tool_result_json is not None


def test_unknown_tool_call_returns_error_to_model(writable_conn, readonly_conn):
    bad_call = ToolCall(id="call_x", name="hack_db", arguments={})
    client = MockAgentClient(
        [
            AgentMessage(content=None, tool_calls=[bad_call], finish_reason="tool_calls"),
            AgentMessage(content="I cannot answer.", tool_calls=[], finish_reason="stop"),
        ]
    )
    loop = _build_loop(writable_conn, readonly_conn, client)
    answer = loop.ask("do something")
    assert any(not r.ok for r in answer.tool_results)
    assert "unknown tool" in (answer.tool_results[0].error or "")


def test_iteration_cap_yields_error(writable_conn, readonly_conn):
    # Always emit a tool call so the loop never finalizes
    forever_call = ToolCall(id="call_x", name="count_ads", arguments={})
    responses = [
        AgentMessage(content=None, tool_calls=[forever_call], finish_reason="tool_calls")
    ] * 5
    config = AgentConfig(max_iterations=3)
    client = MockAgentClient(responses)
    loop = _build_loop(writable_conn, readonly_conn, client, config)
    answer = loop.ask("loop forever")
    assert answer.error == "iteration_cap_reached"


def test_event_ordering(writable_conn, readonly_conn):
    tool_call = ToolCall(id="c1", name="count_ads", arguments={})
    client = MockAgentClient(
        [
            AgentMessage(content=None, tool_calls=[tool_call], finish_reason="tool_calls"),
            AgentMessage(content="ok", tool_calls=[], finish_reason="stop"),
        ]
    )
    loop = _build_loop(writable_conn, readonly_conn, client)
    events = list(loop.stream("hi"))
    types = [e.type for e in events]
    assert types[0] == "session"
    # User message echo
    assert types[1] == "message"
    # Then a tool_call followed by tool_result
    tc_index = types.index("tool_call")
    tr_index = types.index("tool_result")
    assert tc_index < tr_index
    # End with final + done
    assert types[-2] == "final"
    assert types[-1] == "done"


def test_history_replay_includes_prior_user_assistant(writable_conn, readonly_conn):
    client = MockAgentClient(
        [
            AgentMessage(content="first", tool_calls=[], finish_reason="stop"),
            AgentMessage(content="second", tool_calls=[], finish_reason="stop"),
        ]
    )
    loop = _build_loop(writable_conn, readonly_conn, client)
    first = loop.ask("hello")
    loop.ask("again", session_id=first.session_id)

    # The second call's `messages` must include the previous user/assistant turns
    second_call_messages = client.calls[1]["messages"]
    contents = [m.get("content") for m in second_call_messages]
    assert "hello" in contents
    assert "first" in contents


def test_truncated_tool_result_propagates(writable_conn, readonly_conn):
    tool_call = ToolCall(
        id="c1", name="list_ads", arguments={"limit": 1}
    )
    client = MockAgentClient(
        [
            AgentMessage(content=None, tool_calls=[tool_call], finish_reason="tool_calls"),
            AgentMessage(content="see one", tool_calls=[], finish_reason="stop"),
        ]
    )
    loop = _build_loop(writable_conn, readonly_conn, client)
    answer = loop.ask("show me")
    assert any(r.truncated for r in answer.tool_results)
    assert answer.truncated is True


def test_malformed_tool_arguments_surface_error(writable_conn, readonly_conn):
    """When the model emits invalid JSON args, the tool gets a structured error."""
    from ad_classifier.agent.client import _coerce_args

    coerced = _coerce_args("not-json")
    assert coerced == {"_raw": "not-json"}

    bad_call = ToolCall(id="c1", name="list_ads", arguments={"_raw": "not-json"})
    client = MockAgentClient(
        [
            AgentMessage(content=None, tool_calls=[bad_call], finish_reason="tool_calls"),
            AgentMessage(content="recovered", tool_calls=[], finish_reason="stop"),
        ]
    )
    loop = _build_loop(writable_conn, readonly_conn, client)
    answer = loop.ask("call list_ads")
    assert answer.tool_results[0].ok is False
    assert "could not parse" in (answer.tool_results[0].error or "")
