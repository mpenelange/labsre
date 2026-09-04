from fastapi.testclient import TestClient

from labsre.dummy_engine import app

client = TestClient(app)


def test_dummy_engine_exposes_only_synthetic_container_state() -> None:
    response = client.get("/v1.52/containers/json", params={"all": "true"})

    assert response.status_code == 200
    containers = response.json()
    assert {item["Names"][0] for item in containers} == {
        "/homepage",
        "/paperless_db",
        "/paperless_web",
    }
    assert next(item for item in containers if item["Names"] == ["/paperless_web"])[
        "State"
    ] == "exited"


def test_dummy_engine_inspect_and_logs_match_the_failure() -> None:
    inspected = client.get("/v1.52/containers/paperless_web/json")
    logs = client.get("/v1.52/containers/paperless_web/logs")

    assert inspected.json()["RestartCount"] == 4
    assert inspected.json()["State"]["ExitCode"] == 1
    assert "connection refused" in logs.text


def test_dummy_engine_is_not_a_write_capable_docker_api() -> None:
    response = client.post("/v1.52/containers/paperless_web/restart")

    assert response.status_code == 404
