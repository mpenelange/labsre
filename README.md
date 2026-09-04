# LabSRE

LabSRE is a replay-first, human-governed homelab incident response agent built with LangGraph and MCP that gathers bounded evidence, recommends allowlisted remediation, pauses for approval, and verifies recovery. The current release includes a Dockerized FastAPI service, deterministic Immich incident scenarios, an MCP server, safety controls, and automated tests; see [the threat model](docs/threat-model.md) before use.
