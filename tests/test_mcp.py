"""Tests for the MCP tool callables."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app import mcp_server
from app.mcp_server import (
    generate_video,
    get_video,
    get_video_status,
    list_history,
    set_azure_service,
)
from app.models import VideoHistoryEntry, VideoStatus


@pytest.fixture
def mock_service():
    """Inject a mock AzureOpenAIService into the MCP module."""
    service = MagicMock()
    set_azure_service(service)
    yield service
    mcp_server._service = None


@pytest.mark.asyncio
async def test_generate_video_tool(mock_service):
    mock_service.generate_video = AsyncMock(return_value="vid-xyz")

    result = await generate_video("a cat playing piano", "1280x720", 4)

    assert result == {"video_id": "vid-xyz", "status": "pending"}
    request = mock_service.generate_video.call_args.args[0]
    assert request.prompt == "a cat playing piano"
    assert request.resolution.value == "1280x720"
    assert request.seconds == 4


@pytest.mark.asyncio
async def test_generate_video_invalid_resolution(mock_service):
    with pytest.raises(ValueError):
        await generate_video("bad", "999x999", 4)


def test_get_video_status_found(mock_service):
    mock_service.get_video_status.return_value = VideoStatus(
        video_id="v1", status="in_progress", progress=42
    )
    result = get_video_status("v1")
    assert result["video_id"] == "v1"
    assert result["status"] == "in_progress"
    assert result["progress"] == 42


def test_get_video_status_missing(mock_service):
    mock_service.get_video_status.return_value = None
    assert get_video_status("nope") == {"error": "not_found", "video_id": "nope"}


def test_list_history(mock_service):
    entry = VideoHistoryEntry(
        video_id="v1",
        prompt="hi",
        resolution="1280x720",
        seconds=4,
        had_input_image=False,
        created_at="2026-07-01T00:00:00+00:00",
        status="completed",
    )
    mock_service.history.get_all_entries.return_value = [entry]
    result = list_history()
    assert isinstance(result, list)
    assert result[0]["video_id"] == "v1"


def test_get_video_available(mock_service):
    mock_service.get_video_status.return_value = VideoStatus(
        video_id="v1", status="completed", progress=100
    )
    mock_service.history.get_video_path.return_value = "/data/videos/v1.mp4"
    result = get_video("v1")
    assert result["available"] is True
    assert result["video_url"] == "/videos/v1"
    assert result["status"] == "completed"


def test_get_video_unavailable(mock_service):
    mock_service.get_video_status.return_value = None
    mock_service.history.get_video_path.return_value = None
    result = get_video("v1")
    assert result["available"] is False
    assert result["video_url"] is None
