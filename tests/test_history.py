"""Tests for new history and video endpoints."""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import VideoHistoryEntry


@pytest.fixture
def client(mock_env_vars):
    """Create a test client for the FastAPI app."""
    with patch("app.services.azure_openai.AzureOpenAI"):
        # Create a mock service with history
        mock_service = MagicMock()
        mock_history = MagicMock()

        # Mock history methods
        mock_history.get_all_entries = MagicMock(return_value=[])
        mock_history.get_video_path = MagicMock(return_value=None)

        mock_service.history = mock_history
        mock_service.cleanup_old_jobs = MagicMock()

        with patch("app.main.azure_service", mock_service):
            client = TestClient(app)
            client.mock_service = mock_service
            yield client


def test_history_endpoint(client):
    """Test that history endpoint returns a list."""
    response = client.get("/history")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    # Initially empty
    assert len(data) == 0


def test_history_endpoint_with_entries(client):
    """Test that history endpoint returns entries when they exist."""
    # Create mock history entries
    mock_entries = [
        VideoHistoryEntry(
            video_id="test-id-1",
            prompt="Test prompt 1",
            resolution="1280x720",
            seconds=4,
            had_input_image=False,
            created_at=datetime.now(timezone.utc),
            status="completed",
            file_path="/tmp/test1.mp4",
            file_size_bytes=1024,
        )
    ]

    client.mock_service.history.get_all_entries.return_value = mock_entries

    response = client.get("/history")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["video_id"] == "test-id-1"
    assert data[0]["prompt"] == "Test prompt 1"


def test_videos_endpoint_not_found(client):
    """Test that videos endpoint returns 404 for non-existent video."""
    response = client.get("/videos/non-existent-id")
    assert response.status_code == 404
    data = response.json()
    assert "not found" in data["detail"].lower()
