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
    method = os.getenv("LABSRE_STRUCTURED_OUTPUT", "json_schema")
    if method not in {"json_schema", "function_calling"}:
        raise ValueError("LABSRE_STRUCTURED_OUTPUT must be json_schema or function_calling")
    options = {
        "model": model_name,
        "temperature": 0,
        "timeout": float(os.getenv("LABSRE_LLM_TIMEOUT", "120")),
        "max_retries": 0,
        "max_tokens": int(os.getenv("LABSRE_LLM_MAX_TOKENS", "4096")),
    }
    base_url = os.getenv("LABSRE_LLM_BASE_URL")
    if base_url:
        options["base_url"] = base_url
    if base_url and base_url.rstrip("/") == "https://openrouter.ai/api/v1":
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError("OpenRouter requires OPENROUTER_API_KEY in the environment")
        options["api_key"] = api_key
    return LangChainPlanner(ChatOpenAI(**options), method=method)


def build_gateway() -> OperationsGateway:
    mcp_url = os.getenv("LABSRE_MCP_URL")
    if mcp_url:
        return HttpMcpGateway(mcp_url)
    if os.getenv("LABSRE_MODE", "replay") == "docker-readonly":
        return DockerReadOnlyGateway()
    return ReplayGateway(scenario_dir())


gateway = build_gateway()
planner = build_planner()
graph = build_agent_graph(gateway, planner)
