"""Tests for FastAPI application."""

import warnings

import pytest
from fastapi.testclient import TestClient

from app.main import __version__, app


@pytest.fixture
def client(mock_env_vars):
    """Create a test client for the FastAPI app (runs the lifespan)."""
    with TestClient(app) as c:
        yield c


def test_health_endpoint(client):
    """Test the health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "azure-openai-sora"
    assert "version" in data
    assert data["version"] == __version__


def test_version_endpoint(client):
    """Test the version endpoint."""
    response = client.get("/version")
    assert response.status_code == 200
    data = response.json()
    assert "version" in data
    assert data["version"] == __version__


def test_lifespan_startup_shutdown(mock_env_vars):
    """Test that the lifespan event properly initializes and cleans up."""
    with TestClient(app) as client:
        # The lifespan context should have initialized the service
        response = client.get("/health")
        assert response.status_code == 200
        # Cleanup happens automatically when context exits


def test_no_deprecation_warnings(mock_env_vars):
    """The app must not emit on_event deprecation warnings."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        TestClient(app)

        deprecation_warnings = [
            warning
            for warning in w
            if issubclass(warning.category, DeprecationWarning)
            and "on_event is deprecated" in str(warning.message)
        ]

        assert (
            len(deprecation_warnings) == 0
        ), f"Found deprecation warnings: {[str(w.message) for w in deprecation_warnings]}"


def test_mcp_mounted():
    """The MCP streamable-HTTP app should be mounted at /mcp."""
    assert any(getattr(r, "path", None) == "/mcp" for r in app.routes)


def test_app_routes_exist(client):
    """Test that all expected routes exist and return proper status codes."""
    # Health endpoint should work
    response = client.get("/health")
    assert response.status_code == 200

    # Generate endpoint should return validation error without proper payload
    response = client.post("/generate")
    assert response.status_code == 422  # Validation error, not 404

    # Status endpoint should return 404 for non-existent video
    response = client.get("/status/non-existent-id")
    assert response.status_code == 404
    data = response.json()
    assert data["detail"] == "Video job not found"
