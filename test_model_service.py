"""
RoadGuard - Model Service Unit & Integration Tests
Validates the FastAPI inference adapter endpoints.
"""

import base64
import os
import pytest
from fastapi.testclient import TestClient

# Configure test environment variables before importing app
os.environ["MODEL_API_TOKEN"] = "test-secret-token-xyz"
os.environ["MODEL_PATH"] = "models/best.pt"
os.environ["MODEL_CONFIDENCE"] = "0.15"

from model_service import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert data["modelConfigured"] is True
    assert data["modelBackend"] == "yolo"
    assert "D00" in data["supportedClasses"]
    assert "D40" in data["supportedClasses"]


def test_inspect_unauthorized():
    payload = {
        "image_base64": "A" * 200,
        "filename": "test.jpg"
    }
    # No auth header
    response = client.post("/api/v1/inspect", json=payload)
    assert response.status_code == 401

    # Wrong auth header
    response = client.post(
        "/api/v1/inspect",
        json=payload,
        headers={"Authorization": "Bearer wrong-token"}
    )
    assert response.status_code == 401


def test_inspect_invalid_base64():
    payload = {
        "image_base64": "not-valid-base-64-string-with-illegal-characters-and-padding-error-exceeding-one-hundred-characters-long-so-pydantic-validation-passes-cleanly!!!@@@###$$$%%%^^^&&&***",
        "filename": "test.jpg"
    }
    response = client.post(
        "/api/v1/inspect",
        json=payload,
        headers={"Authorization": "Bearer test-secret-token-xyz"}
    )
    assert response.status_code == 400


def test_inspect_valid_image():
    sample_file = "samples/sample_linear_cracks.jpg"
    with open(sample_file, "rb") as f:
        img_bytes = f.read()
    b64_str = base64.b64encode(img_bytes).decode("utf-8")

    payload = {
        "image_base64": b64_str,
        "filename": "sample_linear_cracks.jpg",
        "metadata": {
            "source": "unit-test",
            "latitude": 12.9716,
            "longitude": 77.5946
        }
    }

    response = client.post(
        "/api/v1/inspect",
        json=payload,
        headers={"Authorization": "Bearer test-secret-token-xyz"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["model"] == "trained-yolo"
    assert "detections" in data
    assert isinstance(data["detections"], list)
    assert len(data["detections"]) > 0
    assert "overall_severity" in data
    assert "damage_area_percentage" in data
    print("\n[PASS] Model Service inspection test succeeded:")
    print("  Severity:", data["overall_severity"])
    print("  Damage Area %:", data["damage_area_percentage"])
    print("  Defects found:", len(data["detections"]))


if __name__ == "__main__":
    test_health_endpoint()
    test_inspect_unauthorized()
    test_inspect_invalid_base64()
    test_inspect_valid_image()
    print("\nALL MODEL SERVICE INTEGRATION TESTS PASSED SUCCESSFULLY!")
