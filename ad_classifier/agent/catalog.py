from __future__ import annotations

from typing import Any

from ad_classifier.agent.models import ToolResult, ToolSpec
from ad_classifier.agent.tools.aggregate import AggregateTool
from ad_classifier.agent.tools.base import AgentTool, ToolContext
from ad_classifier.agent.tools.compare_ads import CompareAdsTool
from ad_classifier.agent.tools.count_ads import CountAdsTool
from ad_classifier.agent.tools.get_ad import GetAdTool
from ad_classifier.agent.tools.get_campaign import GetCampaignTool, ListCampaignsTool
from ad_classifier.agent.tools.list_ads import ListAdsTool
from ad_classifier.agent.tools.search import HybridSearchTool, VectorSimilarityTool
from ad_classifier.agent.tools.sql_readonly import SqlReadonlyTool


def default_tools() -> list[AgentTool]:
    return [
        ListAdsTool(),
        CountAdsTool(),
        GetAdTool(),
        ListCampaignsTool(),
        GetCampaignTool(),
        AggregateTool(),
        HybridSearchTool(),
        VectorSimilarityTool(),
        CompareAdsTool(),
        SqlReadonlyTool(),
    ]


class ToolCatalog:
    """Holds the registered tools and dispatches calls to them."""

    def __init__(self, tools: list[AgentTool] | None = None) -> None:
        self._tools: dict[str, AgentTool] = {}
        for tool in tools or default_tools():
            self.register(tool)

    def register(self, tool: AgentTool) -> None:
        self._tools[tool.name] = tool

    def names(self) -> list[str]:
        return list(self._tools)

    def get(self, name: str) -> AgentTool | None:
        return self._tools.get(name)

    def specs(self) -> list[ToolSpec]:
        return [tool.spec() for tool in self._tools.values()]

    def openai_tools(self) -> list[dict[str, Any]]:
        return [spec.to_openai() for spec in self.specs()]

    def call(self, name: str, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(name=name, ok=False, error=f"unknown tool: {name}")
        try:
            return tool.call(args or {}, ctx)
        except Exception as exc:
            return ToolResult(name=name, ok=False, error=f"{type(exc).__name__}: {exc}")

    def render_text_summary(self) -> str:
        lines: list[str] = []
        for tool in self._tools.values():
            params = tool.parameters().get("properties", {})
            arg_names = ", ".join(params.keys()) if params else ""
            lines.append(f"- {tool.name}({arg_names}): {tool.description}")
        return "\n".join(lines)
