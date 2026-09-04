from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Response

app = FastAPI(title="LabSRE Dummy Docker Engine", docs_url=None, redoc_url=None)

_CREATED = 1_788_500_000
_STARTED = "2026-09-04T04:45:00.000000000Z"
_FINISHED = "2026-09-04T04:46:12.000000000Z"

_CONTAINERS: dict[str, dict[str, Any]] = {
    "paperless_web": {
        "image": "dummy/paperless-web:1",
        "project": "dummy-homelab",
        "state": "exited",
        "status": "Exited (1) 40 minutes ago",
        "health": None,
        "restart_count": 4,
        "exit_code": 1,
        "logs": (
            "2026-09-04T04:46:11Z ERROR token=demo-token database connection refused\n"
            "2026-09-04T04:46:12Z FATAL worker stopped\n"
        ),
    },
    "paperless_db": {
        "image": "dummy/postgres:16",
        "project": "dummy-homelab",
        "state": "running",
        "status": "Up 45 minutes (healthy)",
        "health": "healthy",
        "restart_count": 0,
        "exit_code": 0,
        "logs": "2026-09-04T05:20:00Z INFO ready to accept connections\n",
    },
    "homepage": {
        "image": "dummy/homepage:1",
        "project": "dummy-homelab",
        "state": "running",
        "status": "Up 45 minutes (healthy)",
        "health": "healthy",
        "restart_count": 0,
        "exit_code": 0,
        "logs": "2026-09-04T05:20:00Z INFO dashboard ready\n",
    },
}


@app.head("/_ping")
@app.get("/_ping")
def ping() -> Response:
    return Response("OK", media_type="text/plain", headers={"API-Version": "1.52"})


@app.get("/version")
@app.get("/{version}/version")
def version(version: str | None = None) -> dict[str, Any]:
    del version
    return {
        "Platform": {"Name": "LabSRE dummy engine"},
        "Version": "29.0.0",
        "ApiVersion": "1.52",
        "MinAPIVersion": "1.24",
        "GitCommit": "dummy",
        "GoVersion": "go1.25",
        "Os": "linux",
        "Arch": "amd64",
        "KernelVersion": "dummy",
        "BuildTime": "2026-09-04T00:00:00Z",
    }


@app.get("/{version}/containers/json")
def containers(version: str, all: bool = False) -> list[dict[str, Any]]:
    del version
    results = []
    for name, item in _CONTAINERS.items():
        if not all and item["state"] != "running":
            continue
        results.append(
            {
                "Id": f"dummy-{name}",
                "Names": [f"/{name}"],
                "Image": item["image"],
                "ImageID": f"sha256:dummy-{name}",
                "Command": "/dummy-entrypoint",
                "Created": _CREATED,
                "Ports": [],
                "Labels": {"com.docker.compose.project": item["project"]},
                "State": item["state"],
                "Status": item["status"],
                "HostConfig": {"NetworkMode": "dummy-homelab_default"},
                "NetworkSettings": {"Networks": {}},
                "Mounts": [],
            }
        )
    return results


@app.get("/{version}/containers/{name}/json")
def inspect_container(version: str, name: str) -> dict[str, Any]:
    del version
    item = _container(name)
    state: dict[str, Any] = {
        "Status": item["state"],
        "Running": item["state"] == "running",
        "Paused": False,
        "Restarting": False,
        "OOMKilled": False,
        "Dead": False,
        "Pid": 100 if item["state"] == "running" else 0,
        "ExitCode": item["exit_code"],
        "Error": "",
        "StartedAt": _STARTED,
        "FinishedAt": _FINISHED if item["state"] != "running" else "0001-01-01T00:00:00Z",
    }
    if item["health"]:
        state["Health"] = {"Status": item["health"], "FailingStreak": 0, "Log": []}
    return {
        "Id": f"dummy-{name}",
        "Name": f"/{name}",
        "State": state,
        "RestartCount": item["restart_count"],
        "Config": {"Tty": True, "Image": item["image"], "Labels": {}},
        "HostConfig": {"NetworkMode": "dummy-homelab_default"},
        "NetworkSettings": {"Networks": {}},
        "Mounts": [],
    }


@app.get("/{version}/containers/{name}/logs")
def logs(version: str, name: str) -> Response:
    del version
    item = _container(name)
    return Response(item["logs"], media_type="application/vnd.docker.raw-stream")


@app.get("/{version}/events")
def events(version: str) -> Response:
    del version
    timestamp = int(datetime.now(UTC).timestamp())
    body = json.dumps(
        {
            "Type": "container",
            "Action": "die",
            "time": timestamp,
            "Actor": {
                "ID": "dummy-paperless_web",
                "Attributes": {"name": "paperless_web"},
            },
        }
    )
    return Response(f"{body}\n", media_type="application/json")


def _container(name: str) -> dict[str, Any]:
    normalized = name.removeprefix("dummy-")
    try:
        return _CONTAINERS[normalized]
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="No such container") from exc


def main() -> None:
    uvicorn.run("labsre.dummy_engine:app", host="0.0.0.0", port=2375)
