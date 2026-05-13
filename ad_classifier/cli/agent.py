from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

agent_app = typer.Typer(
    name="agent",
    help="NL agent — ask questions about the local ads database.",
    no_args_is_help=True,
)


def _load_loop_for_cli(config_path: Path | None):
    """Build an AgentLoop with a real LM Studio client. Used by `ask` and `repl`."""
    from ad_classifier.agent.catalog import ToolCatalog  # noqa: PLC0415
    from ad_classifier.agent.client import HTTPAgentClient  # noqa: PLC0415
    from ad_classifier.agent.loop import AgentLoop, AgentRunContext  # noqa: PLC0415
    from ad_classifier.api.factories import (  # noqa: PLC0415
        text_embedder_factory,
        vector_store_factory,
        visual_text_embedder_factory,
    )
    from ad_classifier.config import load_config, resolve_config_path  # noqa: PLC0415
    from ad_classifier.db.connection import (  # noqa: PLC0415
        initialize_database,
        open_database,
        open_readonly_database,
    )

    config, config_file = load_config(config_path)
    db_path = resolve_config_path(config.paths.sqlite_path, config_file)
    initialize_database(db_path)
    persistence = open_database(db_path)
    tool_conn = open_readonly_database(db_path)
    catalog = ToolCatalog()
    client = HTTPAgentClient(
        endpoint=config.agent.endpoint.endpoint,
        model=config.agent.endpoint.model,
        api_key_env=config.agent.endpoint.api_key_env,
        timeout_s=config.agent.endpoint.timeout_s,
        max_retries=config.agent.endpoint.max_retries,
        retry_delay_s=config.agent.endpoint.retry_delay_s,
        temperature=config.agent.temperature,
        max_tokens=config.agent.max_tokens,
    )
    run = AgentRunContext(
        persistence_conn=persistence,
        tool_conn=tool_conn,
        catalog=catalog,
        client=client,
        config=config.agent,
        text_embedder_factory=lambda: text_embedder_factory(config),
        visual_text_embedder_factory=lambda: visual_text_embedder_factory(config),
        vector_store_factory=lambda conn: vector_store_factory(config, conn),
    )
    return AgentLoop(run), persistence, tool_conn


@agent_app.command("ask")
def ask(
    question: Annotated[str, typer.Argument(help="The question to ask the agent.")],
    config: Annotated[
        Path | None, typer.Option("--config", "-c", help="Path to config.yaml.")
    ] = None,
    session: Annotated[
        str | None, typer.Option("--session", help="Reuse an existing session id.")
    ] = None,
) -> None:
    """Ask a one-shot question and print the agent's answer."""
    loop, persistence, tool_conn = _load_loop_for_cli(config)
    try:
        answer = loop.ask(question, session_id=session)
    finally:
        persistence.close()
        tool_conn.close()
    typer.echo(f"session={answer.session_id} iterations={answer.iterations}")
    if answer.tool_calls:
        typer.echo(f"tools_called={','.join(call.name for call in answer.tool_calls)}")
    if answer.error:
        typer.echo(f"error={answer.error}", err=True)
    typer.echo(answer.text)


@agent_app.command("repl")
def repl(
    config: Annotated[
        Path | None, typer.Option("--config", "-c", help="Path to config.yaml.")
    ] = None,
) -> None:
    """Interactive REPL — keeps a single session for the duration of the loop."""
    loop, persistence, tool_conn = _load_loop_for_cli(config)
    typer.echo("ad-classifier agent REPL — type 'exit' or Ctrl+C to quit.")
    session_id: str | None = None
    try:
        while True:
            try:
                question = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                typer.echo("")
                break
            if not question or question.lower() in {"exit", "quit"}:
                break
            answer = loop.ask(question, session_id=session_id)
            session_id = answer.session_id
            typer.echo(answer.text)
    finally:
        persistence.close()
        tool_conn.close()


@agent_app.command("show-tools")
def show_tools() -> None:
    """Print every registered tool, its description, and JSON Schema."""
    from ad_classifier.agent.catalog import ToolCatalog  # noqa: PLC0415

    catalog = ToolCatalog()
    for spec in catalog.specs():
        typer.echo(f"\n## {spec.name}")
        typer.echo(spec.description)
        typer.echo(json.dumps(spec.parameters, indent=2))


@agent_app.command("show-schema")
def show_schema(
    config: Annotated[
        Path | None, typer.Option("--config", "-c", help="Path to config.yaml.")
    ] = None,
) -> None:
    """Print the auto-rendered DB schema summary the agent sees."""
    from ad_classifier.agent.catalog import ToolCatalog  # noqa: PLC0415
    from ad_classifier.agent.prompt import render_agent_prompt  # noqa: PLC0415
    from ad_classifier.agent.schema import render_schema_summary  # noqa: PLC0415
    from ad_classifier.config import load_config, resolve_config_path  # noqa: PLC0415
    from ad_classifier.db.connection import (  # noqa: PLC0415
        initialize_database,
        open_readonly_database,
    )

    cfg, config_file = load_config(config)
    db_path = resolve_config_path(cfg.paths.sqlite_path, config_file)
    initialize_database(db_path)
    conn = open_readonly_database(db_path)
    try:
        summary = render_schema_summary(conn)
        typer.echo("# Schema summary\n")
        typer.echo(summary)
        typer.echo("\n# Rendered system prompt\n")
        typer.echo(render_agent_prompt(ToolCatalog(), summary))
    finally:
        conn.close()
