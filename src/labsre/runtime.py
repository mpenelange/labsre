from __future__ import annotations

import os
from pathlib import Path

from labsre.agent_workflow import build_agent_graph
from labsre.docker_readonly import DockerReadOnlyGateway
from labsre.gateway import OperationsGateway
from labsre.mcp_gateway import HttpMcpGateway
from labsre.planner import HeuristicPlanner, LangChainPlanner, Planner
from labsre.replay import ReplayGateway


def scenario_dir() -> Path:
    configured = os.getenv("LABSRE_SCENARIO_DIR")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2] / "scenarios"


def build_planner() -> Planner:
    model_name = os.getenv("LABSRE_MODEL")
    if not model_name:
        return HeuristicPlanner()
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        raise RuntimeError(
            "LABSRE_MODEL requires the LLM extra: uv sync --extra llm"
        ) from exc
    return LangChainPlanner(ChatOpenAI(model=model_name, temperature=0))


def build_gateway() -> OperationsGateway:
    if os.getenv("LABSRE_MODE", "replay") == "docker-readonly":
        return DockerReadOnlyGateway()
    mcp_url = os.getenv("LABSRE_MCP_URL")
    if mcp_url:
        return HttpMcpGateway(mcp_url)
    return ReplayGateway(scenario_dir())


gateway = build_gateway()
planner = build_planner()
graph = build_agent_graph(gateway, planner)
