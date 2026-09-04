from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from labsre.models import (
    DiscoveredService,
    ExecutionResult,
    FilesystemUsage,
    LogEvent,
    ServiceDependency,
    ServiceEvent,
    ServiceStatus,
    Severity,
)

CommandRunner = Callable[[list[str]], str]

_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization:\s*bearer\s+)[^\s]+"),
    re.compile(r"(?i)((?:password|passwd|secret|api[_-]?key|token)\s*[=:]\s*)[^\s,;]+"),
)


class DockerReadOnlyGateway:
    """Narrow Docker diagnostics adapter with no write implementation."""

    def __init__(
        self,
        *,
        runner: CommandRunner | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._runner = runner or self._run
        self._now = now or (lambda: datetime.now(UTC))

    def list_services(self, scenario_id: str) -> list[DiscoveredService]:
        del scenario_id
        template = (
            '{{.Names}}\t{{.State}}\t{{.Status}}\t{{.Image}}\t'
            '{{.Label "com.docker.compose.project"}}'
        )
        output = self._runner(["docker", "ps", "--all", "--format", template])
        observed_at = self._timestamp()
        services = []
        for line in output.splitlines():
            if not line.strip():
                continue
            name, state, status_text, image, project = (line.split("\t") + [""] * 5)[:5]
            services.append(
                DiscoveredService(
                    service=name,
                    state=state,
                    health=_health_from_status(state, status_text),
                    restart_count=self._restart_count(name),
                    observed_at=observed_at,
                    description=f"Container image {image}",
                    project=project or None,
                    criticality="unknown",
                    user_facing=False,
                    dependencies=[],
                    tags=[],
                )
            )
        return sorted(services, key=lambda item: item.service)

    def get_service_status(self, scenario_id: str, service: str) -> ServiceStatus:
        del scenario_id
        _validate_service(service)
        template = (
            "{{.State.Status}}\t"
            "{{if .State.Health}}{{.State.Health.Status}}{{end}}\t"
            "{{.RestartCount}}"
        )
        output = self._runner(["docker", "inspect", "--format", template, service]).strip()
        state, health, restarts = (output.split("\t") + ["", "0"])[:3]
        return ServiceStatus(
            service=service,
            state=state,
            health=health or None,
            restart_count=int(restarts),
            observed_at=self._timestamp(),
        )

    def get_service_dependencies(
        self, scenario_id: str, service: str
    ) -> list[ServiceDependency]:
        del scenario_id
        _validate_service(service)
        # Docker does not retain Compose depends_on semantics. A later catalog adapter will
        # enrich this without reading arbitrary Compose files.
        return []

    def get_recent_events(
        self, scenario_id: str, service: str, limit: int = 50
    ) -> list[ServiceEvent]:
        del scenario_id
        _validate_service(service)
        if not 1 <= limit <= 100:
            raise ValueError("event limit must be between 1 and 100")
        since = (self._now() - timedelta(minutes=15)).isoformat()
        until = self._now().isoformat()
        template = "{{.Time}}\t{{.Action}}\t{{.Actor.Attributes.name}}"
        output = self._runner(
            [
                "docker",
                "events",
                "--since",
                since,
                "--until",
                until,
                "--filter",
                f"container={service}",
                "--format",
                template,
            ]
        )
        events = []
        for line in output.splitlines()[-limit:]:
            timestamp, action, name = (line.split("\t") + ["", ""])[:3]
            events.append(
                ServiceEvent(
                    service=service,
                    timestamp=timestamp or self._timestamp(),
                    event_type=action or "unknown",
                    message=f"Docker reported {action or 'an event'} for {name or service}",
                )
            )
        return list(reversed(events))

    def get_service_logs(self, scenario_id: str, service: str) -> list[LogEvent]:
        del scenario_id
        _validate_service(service)
        output = self._runner(
            ["docker", "logs", "--timestamps", "--since", "15m", "--tail", "200", service]
        )
        events = []
        for line in output.splitlines():
            timestamp, _, message = line.partition(" ")
            clean = _redact(message or timestamp)[:2_000]
            lower = clean.lower()
            severity = (
                Severity.CRITICAL
                if any(word in lower for word in ("fatal", "panic", "critical"))
                else Severity.WARNING
                if any(word in lower for word in ("error", "warn", "failed"))
                else Severity.INFO
            )
            events.append(
                LogEvent(
                    service=service,
                    timestamp=timestamp if message else self._timestamp(),
                    severity=severity,
                    message=clean,
                )
            )
        return events

    def get_filesystem_usage(self, scenario_id: str) -> list[FilesystemUsage]:
        del scenario_id
        output = self._runner(["df", "-P", "-k"])
        observed_at = self._timestamp()
        filesystems = []
        for line in output.splitlines()[1:]:
            columns = line.split()
            if len(columns) < 6 or not columns[4].endswith("%"):
                continue
            filesystems.append(
                FilesystemUsage(
                    host="docker",
                    mount=columns[5],
                    used_percent=float(columns[4].rstrip("%")),
                    available_gb=int(columns[3]) / 1024 / 1024,
                    observed_at=observed_at,
                )
            )
        return filesystems

    def get_permitted_actions(self, scenario_id: str, service: str) -> list[str]:
        del scenario_id
        _validate_service(service)
        return []

    def restart_service(self, scenario_id: str, service: str) -> ExecutionResult:
        del scenario_id
        _validate_service(service)
        raise PermissionError("live remediation is disabled in docker-readonly mode")

    def _restart_count(self, service: str) -> int:
        template = "{{.RestartCount}}"
        value = self._runner(["docker", "inspect", "--format", template, service]).strip()
        return int(value or 0)

    def _timestamp(self) -> str:
        return self._now().isoformat().replace("+00:00", "Z")

    @staticmethod
    def _run(arguments: list[str]) -> str:
        result = subprocess.run(
            arguments,
            capture_output=True,
            check=True,
            text=True,
            timeout=8,
        )
        output = f"{result.stdout}{result.stderr}"
        if len(output) > 1_000_000:
            raise RuntimeError("diagnostic command exceeded the one-megabyte output limit")
        return output


def _validate_service(service: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", service):
        raise ValueError("invalid Docker service name")


def _health_from_status(state: str, status: str) -> str | None:
    match = re.search(r"\((healthy|unhealthy|starting)\)", status)
    if match:
        return match.group(1)
    return "unhealthy" if state in {"dead", "exited", "restarting"} else None


def _redact(message: str) -> str:
    for pattern in _SECRET_PATTERNS:
        message = pattern.sub(r"\1[REDACTED]", message)
    return message
