"""Tests for Azure OpenAI service."""

import logging
from unittest.mock import MagicMock, patch

import pytest

from app.models import VideoGenerationRequest, VideoResolution
from app.services.azure_openai import AzureOpenAIService


@pytest.fixture
def azure_service(mock_env_vars):
    """Create an Azure OpenAI service instance for testing."""
    with patch("app.services.azure_openai.AzureOpenAI"):
        service = AzureOpenAIService()
        # Mock the client.videos methods
        service.client = MagicMock()
        service.client.videos = MagicMock()
        service.client.videos.create = MagicMock()
        service.client.videos.retrieve = MagicMock()
        service.client.videos.download_content = MagicMock()
        return service


@pytest.mark.asyncio
async def test_generate_video_success(azure_service: AzureOpenAIService):
    """Test successful video generation."""
    request = VideoGenerationRequest(
        prompt="A beautiful sunset",
        resolution=VideoResolution.LANDSCAPE,
        seconds=4,
    )

    with patch.object(azure_service, "_generate_video_async") as mock_async:
        mock_async.return_value = None

        video_id = await azure_service.generate_video(request)

        assert video_id is not None
        assert video_id in azure_service.video_jobs
        assert azure_service.video_jobs[video_id].status == "pending"


def test_call_sora_api_success(azure_service: AzureOpenAIService):
    """Test successful Sora 2 API call."""
    request = VideoGenerationRequest(
        prompt="A beautiful sunset",
        resolution=VideoResolution.LANDSCAPE,
        seconds=4,
    )

    # Mock the API response for Sora 2
    mock_video = MagicMock()
    mock_video.id = "video_123456"
    mock_video.status = "queued"
    mock_video.progress = 0

    azure_service.client.videos.create.return_value = mock_video

    result = azure_service._call_sora_api(request)

    assert result is not None
    assert result["id"] == "video_123456"
    assert result["status"] == "queued"

    # Verify the API was called with correct parameters
    azure_service.client.videos.create.assert_called_once_with(
        model="sora-2",
        prompt="A beautiful sunset",
        size="1280x720",
        seconds="4",
    )


def test_call_sora_api_failure(azure_service: AzureOpenAIService):
    """Test Sora 2 API call failure."""
    request = VideoGenerationRequest(
        prompt="A beautiful sunset",
        resolution=VideoResolution.LANDSCAPE,
        seconds=4,
    )

    # Mock API exception
    azure_service.client.videos.create.side_effect = Exception("API Error")

    with pytest.raises(Exception, match="API Error"):
        azure_service._call_sora_api(request)


def test_call_sora_api_with_input_image(azure_service: AzureOpenAIService):
    """Test Sora 2 API call with input reference image."""
    # Create a mock image data
    mock_image_data = b"fake_image_data"

    request = VideoGenerationRequest(
        prompt="Continue the scene",
        resolution=VideoResolution.LANDSCAPE,
        seconds=4,
        input_image_data=mock_image_data,
    )

    # Mock the API response for Sora 2
    mock_video = MagicMock()
    mock_video.id = "video_with_image_123"
    mock_video.status = "queued"
    mock_video.progress = 0

    azure_service.client.videos.create.return_value = mock_video

    result = azure_service._call_sora_api(request)

    assert result is not None
    assert result["id"] == "video_with_image_123"
    assert result["status"] == "queued"

    # Verify the API was called with input_reference parameter
    call_args = azure_service.client.videos.create.call_args
    assert call_args is not None
    assert "input_reference" in call_args.kwargs
    # Check that input_reference is a file-like object
    assert hasattr(call_args.kwargs["input_reference"], "read")


def test_get_video_status_existing(azure_service: AzureOpenAIService):
    """Test getting status for existing video job."""
    from app.models import VideoStatus

    test_status = VideoStatus(video_id="test-id", status="processing", progress=50)

    azure_service.video_jobs["test-id"] = test_status

    result = azure_service.get_video_status("test-id")

    assert result == test_status
    assert result.video_id == "test-id"
    assert result.status == "processing"
    assert result.progress == 50


def test_get_video_status_non_existent(azure_service: AzureOpenAIService):
    """Test getting status for non-existent video job."""
    result = azure_service.get_video_status("non-existent-id")
    assert result is None


def test_cleanup_old_jobs(azure_service: AzureOpenAIService):
    """Test cleanup of old video jobs."""
    from app.models import VideoStatus

    # Add many jobs to trigger cleanup
    for i in range(150):
        job_id = f"job-{i}"
        azure_service.video_jobs[job_id] = VideoStatus(
            video_id=job_id, status="completed", progress=100
        )

    initial_count = len(azure_service.video_jobs)
    assert initial_count == 150

    azure_service.cleanup_old_jobs()

    # Should keep only 50 most recent jobs
    assert len(azure_service.video_jobs) == 50


def test_service_initialization_logging(mock_env_vars, caplog):
    """Test that service initialization logs correctly."""
    with patch("app.services.azure_openai.AzureOpenAI"):
        with caplog.at_level(logging.INFO):
            _ = AzureOpenAIService()

            # Check that initialization log was created
            assert any(
                "Azure OpenAI Service initialized" in record.message
                for record in caplog.records
            )
            assert any(
                "Endpoint: https://test.openai.azure.com/" in record.message
                for record in caplog.records
            )
            assert any(
                "Model: sora-2" in record.message for record in caplog.records
            )
            # Check that API key is masked (either *** for short keys or partial masking for long keys)
            assert any(
                "API Key:" in record.message and "***" in record.message
                for record in caplog.records
            )
            # Ensure full API key is NOT logged
            assert not any(
                "test-key-12345678" in record.message for record in caplog.records
            )


def test_call_sora_api_logging(azure_service: AzureOpenAIService, caplog):
    """Test that API calls are logged with details."""
    request = VideoGenerationRequest(
        prompt="A beautiful sunset",
        resolution=VideoResolution.LANDSCAPE,
        seconds=4,
    )

    # Mock response
    mock_response = MagicMock()
    mock_response.id = "test-video-id"
    mock_response.status = "queued"
    azure_service.client.videos.create.return_value = mock_response
    azure_service.client.base_url = "https://test.openai.azure.com/"
    azure_service.client._custom_query = {"api-version": "2024-08-01-preview"}

    with caplog.at_level(logging.INFO):
        _ = azure_service._call_sora_api(request)

        # Check that API call was logged
        assert any(
            "Calling Sora API with text-to-video" in record.message
            for record in caplog.records
        )
        assert any(
            "Prompt: 'A beautiful sunset'" in record.message
            for record in caplog.records
        )
        assert any("Resolution: 1280x720" in record.message for record in caplog.records)
        assert any("Duration: 4s" in record.message for record in caplog.records)

        # Check that response was logged
        assert any(
            "Sora API response received" in record.message for record in caplog.records
        )
        assert any(
            "Video ID: test-video-id" in record.message for record in caplog.records
        )
