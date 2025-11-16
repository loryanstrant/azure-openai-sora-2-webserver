"""Integration tests for the FastAPI application."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client(mock_env_vars):
    """Create a test client for integration tests."""
    with patch("app.services.azure_openai.OpenAI"):
        # Create a mock service instance
        mock_service = MagicMock()

        # Make the async methods return coroutines
        async def mock_generate_video(request):
            return "test-video-id-123"

        mock_service.generate_video = mock_generate_video
        mock_service.get_video_status = MagicMock()
        mock_service.cleanup_old_jobs = MagicMock()

        # Patch the global service at module level
        with patch("app.main.azure_service", mock_service):
            client = TestClient(app)
            # Store the mock service for use in tests
            client.mock_service = mock_service
            yield client


def test_root_endpoint_serves_web_interface(client):
    """Test that the root endpoint serves the web interface."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Azure OpenAI Sora Video Generator" in response.text


def test_generate_video_integration(client):
    """Test complete video generation workflow integration."""
    # The async mock is already set up in the fixture

    # Test video generation request
    response = client.post(
        "/generate",
        json={
            "prompt": "A beautiful sunset over the ocean",
            "resolution": "1280x720",
            "seconds": 4,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["video_id"] == "test-video-id-123"
    assert data["status"] == "pending"


def test_generate_video_validation_errors(client):
    """Test video generation with invalid input."""
    # Missing required fields
    response = client.post("/generate", json={})
    assert response.status_code == 422

    # Invalid resolution
    response = client.post(
        "/generate",
        json={
            "prompt": "Test prompt",
            "resolution": "invalid-resolution",
            "seconds": 4,
        },
    )
    assert response.status_code == 422

    # Invalid seconds (negative)
    response = client.post(
        "/generate",
        json={"prompt": "Test prompt", "resolution": "1280x720", "seconds": -1},
    )
    assert response.status_code == 422


def test_video_status_integration(client):
    """Test video status endpoint integration."""
    from app.models import VideoStatus

    # Mock existing video
    mock_status = VideoStatus(
        video_id="test-id",
        status="processing",
        progress=50,
        video_url=None,
        revised_prompt=None,
    )
    client.mock_service.get_video_status.return_value = mock_status

    response = client.get("/status/test-id")
    assert response.status_code == 200
    data = response.json()
    assert data["video_id"] == "test-id"
    assert data["status"] == "processing"
    assert data["progress"] == 50

    # Test non-existent video
    client.mock_service.get_video_status.return_value = None
    response = client.get("/status/non-existent")
    assert response.status_code == 404
    assert response.json()["detail"] == "Video job not found"


def test_api_error_handling(client):
    """Test API error handling."""

    # Override the mock to raise an exception
    async def mock_generate_video_error(request):
        raise Exception("Azure API Error")

    client.mock_service.generate_video = mock_generate_video_error

    response = client.post(
        "/generate",
        json={"prompt": "Test prompt", "resolution": "1280x720", "seconds": 4},
    )

    assert response.status_code == 500
    assert "Azure API Error" in response.json()["detail"]


def test_cors_and_content_types(client):
    """Test CORS headers and content types."""
    # Test JSON endpoints
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"

    # Test HTML endpoint
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_complete_video_workflow_simulation(client):
    """Test a complete video generation workflow from start to finish."""
    from app.models import VideoStatus

    # Override the mock for this test
    async def mock_generate_workflow(request):
        return "workflow-test-id"

    client.mock_service.generate_video = mock_generate_workflow

    # Step 1: Generate video
    response = client.post(
        "/generate",
        json={
            "prompt": "A cat playing with yarn",
            "resolution": "1280x720",
            "seconds": 4,
        },
    )

    assert response.status_code == 200
    video_id = response.json()["video_id"]
    assert video_id == "workflow-test-id"

    # Step 2: Check initial status (pending)
    client.mock_service.get_video_status.return_value = VideoStatus(
        video_id=video_id, status="pending", progress=0
    )

    response = client.get(f"/status/{video_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    assert response.json()["progress"] == 0

    # Step 3: Check processing status
    client.mock_service.get_video_status.return_value = VideoStatus(
        video_id=video_id, status="processing", progress=50
    )

    response = client.get(f"/status/{video_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "processing"
    assert response.json()["progress"] == 50

    # Step 4: Check completed status
    client.mock_service.get_video_status.return_value = VideoStatus(
        video_id=video_id,
        status="completed",
        progress=100,
        video_url="https://example.com/video.mp4",
        revised_prompt="A playful orange cat with yarn in a cozy room",
    )

    response = client.get(f"/status/{video_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["progress"] == 100
    assert data["video_url"] == "https://example.com/video.mp4"
    assert "playful orange cat" in data["revised_prompt"]


def test_static_file_serving(client):
    """Test that static files are served correctly."""
    # Test CSS, JS and other static content is accessible
    response = client.get("/static/index.html")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Azure OpenAI Sora Video Generator" in response.text
