"""Tests for custom video URL functionality."""

import logging
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.models import VideoGenerationRequest, VideoResolution
from app.services.azure_openai import AzureOpenAIService


@pytest.fixture
def mock_env_vars_custom_url():
    """Mock environment variables for custom URL testing."""
    with patch.dict(
        "os.environ",
        {
            "AZURE_OPENAI_API_KEY": "test-api-key",
            "AZURE_OPENAI_VIDEO_URL": "https://lorya-mg1r7mj6-swedencentral.cognitiveservices.azure.com/openai/v1/videos",
            "AZURE_OPENAI_DEPLOYMENT": "sora-2",
        },
    ):
        yield


def test_service_initialization_with_custom_url(mock_env_vars_custom_url):
    """Test that service initializes correctly with custom video URL."""
    with patch("app.services.azure_openai.AzureOpenAI"):
        service = AzureOpenAIService()

        assert service.custom_video_url == "https://lorya-mg1r7mj6-swedencentral.cognitiveservices.azure.com/openai/v1/videos"
        assert service.api_key == "test-api-key"
        assert service.model == "sora-2"


def test_service_initialization_custom_url_requires_protocol(mock_env_vars_custom_url):
    """Test that custom URL must have http:// or https:// protocol."""
    with patch.dict(
        "os.environ",
        {
            "AZURE_OPENAI_API_KEY": "test-api-key",
            "AZURE_OPENAI_VIDEO_URL": "lorya-mg1r7mj6-swedencentral.cognitiveservices.azure.com/openai/v1/videos",
        },
    ):
        with pytest.raises(ValueError, match="must start with 'http://' or 'https://'"):
            AzureOpenAIService()


def test_service_initialization_custom_url_logging(mock_env_vars_custom_url, caplog):
    """Test that custom URL initialization is logged."""
    with patch("app.services.azure_openai.AzureOpenAI"):
        with caplog.at_level(logging.INFO):
            _ = AzureOpenAIService()

            # Check that custom URL log was created
            assert any(
                "Azure OpenAI Service initialized with custom video URL" in record.message
                for record in caplog.records
            )
            assert any(
                "Video URL: https://lorya-mg1r7mj6-swedencentral.cognitiveservices.azure.com/openai/v1/videos" in record.message
                for record in caplog.records
            )


def test_call_sora_api_with_custom_url(mock_env_vars_custom_url):
    """Test Sora API call with custom URL uses HTTP client."""
    with patch("app.services.azure_openai.AzureOpenAI"):
        service = AzureOpenAIService()

        request = VideoGenerationRequest(
            prompt="A beautiful sunset",
            resolution=VideoResolution.LANDSCAPE,
            seconds=4,
        )

        # Mock httpx response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": "video_custom_123",
            "status": "queued",
            "progress": 0,
        }
        mock_response.status_code = 200

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            result = service._call_sora_api(request)

            # Verify HTTP request was made
            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args

            # Check URL
            assert call_args[0][0] == "https://lorya-mg1r7mj6-swedencentral.cognitiveservices.azure.com/openai/v1/videos"

            # Check headers
            assert "headers" in call_args[1]
            assert call_args[1]["headers"]["api-key"] == "test-api-key"
            assert call_args[1]["headers"]["Content-Type"] == "application/json"

            # Check body
            assert "json" in call_args[1]
            body = call_args[1]["json"]
            assert body["model"] == "sora-2"
            assert body["prompt"] == "A beautiful sunset"
            assert body["size"] == "1280x720"
            assert body["seconds"] == "4"

            # Check result
            assert result["id"] == "video_custom_123"
            assert result["status"] == "queued"


def test_call_sora_api_custom_url_http_error(mock_env_vars_custom_url):
    """Test that HTTP errors are properly handled with custom URL."""
    with patch("app.services.azure_openai.AzureOpenAI"):
        service = AzureOpenAIService()

        request = VideoGenerationRequest(
            prompt="A beautiful sunset",
            resolution=VideoResolution.LANDSCAPE,
            seconds=4,
        )

        # Mock httpx error response
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Resource Not Found"

        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__.return_value = mock_client
            mock_client.post.side_effect = httpx.HTTPStatusError(
                "404 Not Found",
                request=MagicMock(),
                response=mock_response,
            )

            with pytest.raises(Exception, match="API request failed with status 404"):
                service._call_sora_api(request)


@pytest.mark.asyncio
async def test_poll_video_status_with_custom_url(mock_env_vars_custom_url):
    """Test polling video status with custom URL."""
    with patch("app.services.azure_openai.AzureOpenAI"):
        service = AzureOpenAIService()

        # Create a test video job
        from app.models import VideoStatus
        video_id = "test-video-id"
        azure_video_id = "azure-video-123"
        service.video_jobs[video_id] = VideoStatus(
            video_id=video_id,
            status="queued",
            progress=10,
        )

        # Mock httpx async response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": azure_video_id,
            "status": "completed",
        }
        mock_response.raise_for_status = MagicMock()

        # Create an async mock client
        async def mock_get(*args, **kwargs):
            return mock_response

        mock_client = MagicMock()
        mock_client.get = mock_get

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_client

            await service._poll_video_status(video_id, azure_video_id)

            # Verify job status was updated
            assert service.video_jobs[video_id].status == "completed"
            assert service.video_jobs[video_id].progress == 100


def test_custom_url_takes_precedence_over_endpoint():
    """Test that custom URL takes precedence when both are provided."""
    with patch.dict(
        "os.environ",
        {
            "AZURE_OPENAI_API_KEY": "test-api-key",
            "AZURE_OPENAI_ENDPOINT": "https://old-endpoint.openai.azure.com/",
            "AZURE_OPENAI_VIDEO_URL": "https://new-endpoint.cognitiveservices.azure.com/openai/v1/videos",
        },
    ):
        with patch("app.services.azure_openai.AzureOpenAI"):
            service = AzureOpenAIService()

            # Custom URL should be used
            assert service.custom_video_url == "https://new-endpoint.cognitiveservices.azure.com/openai/v1/videos"


def test_legacy_mode_still_works_without_custom_url():
    """Test that legacy mode (without custom URL) still works."""
    with patch.dict(
        "os.environ",
        {
            "AZURE_OPENAI_API_KEY": "test-api-key",
            "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com/",
            "AZURE_OPENAI_DEPLOYMENT": "sora-2",
        },
    ):
        with patch("app.services.azure_openai.AzureOpenAI") as mock_azure_openai:
            service = AzureOpenAIService()

            # Should not have custom URL
            assert service.custom_video_url is None

            # Should use SDK client
            mock_azure_openai.assert_called_once()
