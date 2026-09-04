import sys
from types import SimpleNamespace

import pytest

from labsre.models import Evidence
from labsre.planner import PlannerOutput
from labsre.runtime import build_planner


@pytest.mark.parametrize("method", ["json_schema", "function_calling"])
def test_custom_endpoint_and_output_method_reach_model(monkeypatch, method):
    captured = {}

    class Model:
        def __init__(self, **options):
            captured.update(options)

        def with_structured_output(self, schema, **options):
            captured["schema"] = schema
            captured["structured"] = options
            return self

        def invoke(self, messages):
            captured["messages"] = messages
            return {
                "situation_summary": "Insufficient evidence.",
                "evidence_sufficient": False,
                "confidence": 0.2,
                "next_tool": None,
                "relevant_service": None,
                "hypotheses": [],
                "reasoning_summary": "No runtime observations available.",
            }

    monkeypatch.setitem(sys.modules, "langchain_openai", SimpleNamespace(ChatOpenAI=Model))
    monkeypatch.setenv("LABSRE_MODEL", "Qwen/Qwen3.8-27B")
    monkeypatch.setenv("LABSRE_LLM_BASE_URL", "http://127.0.0.1:1234/v1")
    monkeypatch.setenv("LABSRE_STRUCTURED_OUTPUT", method)
    monkeypatch.setenv("LABSRE_LLM_TIMEOUT", "60")
    monkeypatch.setenv("LABSRE_LLM_MAX_TOKENS", "2048")
    planner = build_planner()
    result = planner.decide(
        objective="Investigate",
        available_tools=["get_recent_events"],
        evidence=[
            Evidence(
                evidence_id="e0",
                source="list_services",
                summary="Empty",
                observed_at="unknown",
                data={"services": []},
            ).model_dump()
        ],
    )
    assert captured["base_url"] == "http://127.0.0.1:1234/v1"
    assert captured["model"] == "Qwen/Qwen3.8-27B"
    assert captured["max_retries"] == 0
    assert captured["timeout"] == 60
    assert captured["max_tokens"] == 2048
    assert captured["schema"] == PlannerOutput.model_json_schema()
    assert captured["structured"] == {"method": method}
    assert '"evidence_id": "e0"' in captured["messages"][1].content
    assert not result.evidence_sufficient


def test_openrouter_requires_its_own_key(monkeypatch):
    monkeypatch.setitem(sys.modules, "langchain_openai", SimpleNamespace(ChatOpenAI=object))
    monkeypatch.setenv("LABSRE_MODEL", "z-ai/glm-5.3-flash")
    monkeypatch.setenv("LABSRE_LLM_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "unrelated-test-key")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="requires OPENROUTER_API_KEY"):
        build_planner()


def test_openrouter_key_and_function_calling_are_forwarded(monkeypatch):
    captured = {}

    class Model:
        def __init__(self, **options):
            captured.update(options)

        def with_structured_output(self, schema, **options):
            captured.update(options)
            return self

    monkeypatch.setitem(sys.modules, "langchain_openai", SimpleNamespace(ChatOpenAI=Model))
    monkeypatch.setenv("LABSRE_MODEL", "z-ai/glm-5.3-flash")
    monkeypatch.setenv("LABSRE_LLM_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("LABSRE_STRUCTURED_OUTPUT", "function_calling")
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-test-key")
    build_planner()
    assert captured["api_key"] == "synthetic-test-key"
    assert captured["method"] == "function_calling"


def test_model_must_explicitly_choose_next_tool_and_service():
    from pydantic import ValidationError

    assert {"next_tool", "relevant_service", "hypotheses"} <= set(
        PlannerOutput.model_json_schema()["required"]
    )
    with pytest.raises(ValidationError):
        PlannerOutput.model_validate_json(
            '{"situation_summary":"Need logs", "evidence_sufficient":false, '
            '"confidence":0.3, "reasoning_summary":"Inspect logs next"}'
        )


def test_real_langchain_parser_accepts_json_arrays_for_strict_tuple_fields():
    import json

    import httpx

    from labsre.planner import LangChainPlanner

    chat = pytest.importorskip("langchain_openai").ChatOpenAI
    output = {
        "situation_summary": "Need service logs.",
        "evidence_sufficient": False,
        "confidence": 0.3,
        "reasoning_summary": "Inspect the cause of failure.",
        "relevant_service": "photos",
        "next_tool": {
            "name": "get_service_logs",
            "arguments": {"service": "photos"},
            "purpose": "Inspect failure logs",
        },
        "hypotheses": [
            {
                "claim": "Service may have failed",
                "status": "possible",
                "supporting_evidence_ids": ["e0"],
                "contradicting_evidence_ids": [],
            }
        ],
    }

    def handle(request):
        return httpx.Response(
            200,
            json={
                "id": "test-response",
                "object": "chat.completion",
                "created": 0,
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "test-call",
                                    "type": "function",
                                    "function": {
                                        "name": "PlannerOutput",
                                        "arguments": json.dumps(output),
                                    },
                                }
                            ],
                        },
                    }
                ],
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        planner = LangChainPlanner(
            chat(model="test-model", api_key="synthetic-test-key", http_client=client),
            method="function_calling",
        )
        result = planner.decide(
            objective="Investigate photos", evidence=[], available_tools=["get_service_logs"]
        )
    assert result.next_tool.arguments == {"service": "photos"}
    assert result.hypotheses[0].supporting_evidence_ids == ("e0",)
