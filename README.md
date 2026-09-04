# LabSRE

LabSRE is a human-governed incident response agent for a homelab. It investigates an
operational objective through bounded MCP tools, assembles evidence, recommends the safest
allowed remediation, pauses for human approval, and verifies the outcome.

The current milestone is a safe replay-mode vertical slice. It diagnoses a container restart
loop caused by disk pressure, requests approval for an allowlisted service restart, and records
the resulting state. It cannot connect to Docker or execute shell commands.

## Safety model

- Read-only diagnostics and consequential remediation are separate capabilities.
- The model never receives a shell or Docker socket.
- Remediation targets and action types are allowlisted.
- Approval is bound to the exact incident, action, target, and parameters.
- State is revalidated immediately before execution.
- Replay mode is the default and only implemented backend in this milestone.

See [docs/threat-model.md](docs/threat-model.md) for the trust boundaries and non-goals.

## Run locally

Python 3.12 and `uv` are recommended:

```bash
uv sync --extra dev
uv run pytest
uv run labsre-api
```

Start an investigation:

```bash
curl -s -X POST http://localhost:8000/incidents/investigate \
  -H 'content-type: application/json' \
  -d '{"scenario_id":"immich-restart-loop","objective":"Diagnose why Immich is unavailable"}'
```

The response includes a `thread_id` and a structured approval request. Resume it with:

```bash
curl -s -X POST http://localhost:8000/incidents/THREAD_ID/decision \
  -H 'content-type: application/json' \
  -d '{"approved":true,"actor":"michael"}'
```

## Architecture

```text
Alert/API -> LangGraph -> diagnostic gateway -> MCP tools -> replay/live backend
                    \-> approval interrupt -> remediation gateway -> verify
```

The gateway protocol deliberately separates graph logic from transport. The production gateway
will call the MCP server over Streamable HTTP; tests use the same service contract in-process.

## Roadmap

1. Add the MCP client gateway and contract tests.
2. Add an LLM planner with structured output and a deterministic fallback.
3. Add runbook retrieval with citations and an insufficient-evidence path.
4. Add persistent checkpoints and append-only audit events.
5. Add a read-only Docker proxy for a designated homelab host.
6. Enable one allowlisted live remediation only after replay evaluation passes.
