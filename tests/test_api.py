from fastapi.testclient import TestClient

from labsre.api import app


def test_api_discovers_service_without_immich_default_and_resumes() -> None:
    client = TestClient(app)
    response = client.post(
        "/incidents/investigate",
        json={
            "scenario_id": "service-stopped",
            "objective": "Find why my document service is unavailable",
        },
    )

    assert response.status_code == 200
    pending = response.json()
    assert pending["status"] == "awaiting_approval"
    assert pending["recommendation"]["action"]["target"] == "paperless_web"

    resumed = client.post(
        f"/incidents/{pending['thread_id']}/decision",
        json={"approved": True, "actor": "api-test"},
    )
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "resolved"
