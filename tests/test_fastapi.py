"""Tests for FastAPI application."""

import warnings
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client(mock_env_vars):
    """Create a test client for the FastAPI app."""
    with patch("app.services.azure_openai.OpenAI"):
        return TestClient(app)


def test_health_endpoint(client):
    """Test the health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "azure-openai-sora"


def test_lifespan_startup_shutdown():
    """Test that the lifespan event properly initializes and cleans up."""
    with patch("app.services.azure_openai.OpenAI"):
        with TestClient(app) as client:
            # The lifespan context should have initialized the service
            response = client.get("/health")
            assert response.status_code == 200
            # Cleanup happens automatically when context exits


def test_no_deprecation_warnings():
    """Test that the FastAPI app doesn't emit deprecation warnings for event handlers."""
    # Capture warnings
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        with patch("app.services.azure_openai.OpenAI"):
            TestClient(app)

        # Check that no deprecation warnings were raised for on_event
        deprecation_warnings = [
            warning
            for warning in w
            if issubclass(warning.category, DeprecationWarning)
            and "on_event is deprecated" in str(warning.message)
        ]

        assert (
            len(deprecation_warnings) == 0
        ), f"Found deprecation warnings: {[str(w.message) for w in deprecation_warnings]}"


def test_app_routes_exist(client):
    """Test that all expected routes exist and return proper status codes."""
    # Health endpoint should work
    response = client.get("/health")
    assert response.status_code == 200

    # Generate endpoint should return validation error without proper payload (but not 404)
    response = client.post("/generate")
    assert response.status_code == 422  # Validation error, not 404

    # Status endpoint should return 404 for non-existent video (service is working)
    response = client.get("/status/non-existent-id")
    assert response.status_code == 404
    data = response.json()
    assert data["detail"] == "Video job not found"
