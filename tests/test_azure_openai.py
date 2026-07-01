"""Tests for the Azure OpenAI Sora 2 service (raw REST via httpx)."""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.models import VideoGenerationRequest, VideoResolution, VideoStatus
from app.services.azure_openai import (
    AzureOpenAIService,
    _normalize_status,
)


@pytest.fixture
def azure_service(mock_env_vars):
    """Create an Azure OpenAI service instance for testing."""
    return AzureOpenAIService()


def _mock_response(json_data=None, content=b"", status_code=200):
    """Build a MagicMock that mimics an httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.content = content
    resp.raise_for_status.return_value = None
    return resp


def _patch_async_client(post=None, get=None):
    """Patch httpx.AsyncClient with mocked post/get and return the context manager."""
    client = MagicMock()
    client.post = AsyncMock(return_value=post)
    client.get = AsyncMock(return_value=get)
    async_cm = MagicMock()
    async_cm.__aenter__ = AsyncMock(return_value=client)
    async_cm.__aexit__ = AsyncMock(return_value=False)
    return patch("httpx.AsyncClient", return_value=async_cm), client


# --------------------------------------------------------------------- config


def test_service_initialization_logging(mock_env_vars, caplog):
    """Initialization should log endpoint/model and mask the API key."""
    with caplog.at_level(logging.INFO):
        _ = AzureOpenAIService()

    assert any("Azure OpenAI Service initialized" in r.message for r in caplog.records)
    assert any(
        "Endpoint: https://test.openai.azure.com" in r.message for r in caplog.records
    )
    assert any("Model: sora-2" in r.message for r in caplog.records)
    assert any("API Key:" in r.message and "***" in r.message for r in caplog.records)
    assert not any("test-api-key" == r.message for r in caplog.records)


def test_endpoint_is_normalized(azure_service: AzureOpenAIService):
    """Trailing slash and any /openai path should be stripped from the base."""
    assert azure_service.endpoint == "https://test.openai.azure.com"
    assert azure_service._jobs_url() == (
        "https://test.openai.azure.com/openai/v1/video/generations/jobs"
        "?api-version=preview"
    )


# --------------------------------------------------------------------- create


@pytest.mark.asyncio
async def test_generate_video_success(azure_service: AzureOpenAIService):
    """generate_video should register a pending job and return its id."""
    request = VideoGenerationRequest(
        prompt="A beautiful sunset",
        resolution=VideoResolution.LANDSCAPE,
        seconds=4,
    )

    with patch.object(azure_service, "_run_job", new=AsyncMock()):
        video_id = await azure_service.generate_video(request)

    assert video_id in azure_service.video_jobs
    assert azure_service.video_jobs[video_id].status == "pending"


@pytest.mark.asyncio
async def test_create_job_builds_correct_body(azure_service: AzureOpenAIService):
    """Text-to-video POST must target the jobs URL with the right body/headers."""
    request = VideoGenerationRequest(
        prompt="A beautiful sunset",
        resolution=VideoResolution.LANDSCAPE,
        seconds=8,
    )
    post_resp = _mock_response({"id": "job_123", "status": "queued"})
    patcher, client = _patch_async_client(post=post_resp)

    with patcher:
        job_id = await azure_service._create_job(request)

    assert job_id == "job_123"
    args, kwargs = client.post.call_args
    assert args[0] == (
        "https://test.openai.azure.com/openai/v1/video/generations/jobs"
        "?api-version=preview"
    )
    assert kwargs["json"] == {
        "prompt": "A beautiful sunset",
        "width": 1280,
        "height": 720,
        "n_seconds": 8,
        "model": "sora-2",
    }
    assert kwargs["headers"]["api-key"] == "test-api-key"


@pytest.mark.asyncio
async def test_create_job_resolution_split(azure_service: AzureOpenAIService):
    """Portrait resolution should map to width=720, height=1280."""
    request = VideoGenerationRequest(
        prompt="tall video",
        resolution=VideoResolution.PORTRAIT,
        seconds=4,
    )
    post_resp = _mock_response({"id": "job_p", "status": "queued"})
    patcher, client = _patch_async_client(post=post_resp)

    with patcher:
        await azure_service._create_job(request)

    body = client.post.call_args.kwargs["json"]
    assert body["width"] == 720
    assert body["height"] == 1280


@pytest.mark.asyncio
async def test_create_job_multipart_when_image(azure_service: AzureOpenAIService):
    """Image-to-video must send multipart files + inpaint_items, no Content-Type."""
    request = VideoGenerationRequest(
        prompt="animate this",
        resolution=VideoResolution.LANDSCAPE,
        seconds=4,
        input_image_data=b"fake_image_bytes",
    )
    post_resp = _mock_response({"id": "job_img", "status": "queued"})
    patcher, client = _patch_async_client(post=post_resp)

    with patcher:
        job_id = await azure_service._create_job(request)

    assert job_id == "job_img"
    kwargs = client.post.call_args.kwargs
    assert "files" in kwargs and kwargs["files"]["files"][1] == b"fake_image_bytes"
    assert kwargs["data"]["width"] == "1280"
    assert kwargs["data"]["n_seconds"] == "4"
    assert isinstance(kwargs["data"]["inpaint_items"], str)
    assert "Content-Type" not in kwargs["headers"]


@pytest.mark.asyncio
async def test_create_job_http_error(azure_service: AzureOpenAIService):
    """A non-2xx create response should raise with the status + body."""
    request = VideoGenerationRequest(
        prompt="boom", resolution=VideoResolution.LANDSCAPE, seconds=4
    )
    err_resp = MagicMock()
    err_resp.status_code = 400
    err_resp.text = "bad request"
    err_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "400", request=MagicMock(), response=err_resp
    )
    patcher, _ = _patch_async_client(post=err_resp)

    with patcher, pytest.raises(Exception, match="400"):
        await azure_service._create_job(request)


# --------------------------------------------------------------------- status


@pytest.mark.parametrize(
    "azure_status,expected",
    [
        ("queued", "queued"),
        ("preprocessing", "in_progress"),
        ("running", "in_progress"),
        ("processing", "in_progress"),
        ("succeeded", "completed"),
        ("failed", "failed"),
        ("cancelled", "cancelled"),
        ("something_new", "in_progress"),
    ],
)
def test_status_normalization(azure_status, expected):
    assert _normalize_status(azure_status) == expected


@pytest.mark.asyncio
async def test_poll_job_success_downloads(azure_service: AzureOpenAIService):
    """On succeeded, poll must download via the generation_id (not the job_id)."""
    video_id = "vid-1"
    azure_service.video_jobs[video_id] = VideoStatus(
        video_id=video_id, status="queued", progress=10
    )

    poll_resp = _mock_response(
        {"status": "succeeded", "generations": [{"id": "gen_abc"}]}
    )
    download_resp = _mock_response(content=b"MP4DATA")
    patcher, client = _patch_async_client(get=None)
    # First GET = poll, second GET = download
    client.get = AsyncMock(side_effect=[poll_resp, download_resp])

    with patcher, patch("asyncio.sleep", new=AsyncMock()):
        await azure_service._poll_job(video_id, "job_xyz")

    status = azure_service.video_jobs[video_id]
    assert status.status == "completed"
    assert status.progress == 100
    assert status.azure_generation_id == "gen_abc"
    # The download URL must use the generation id, not the job id.
    download_url = client.get.call_args_list[-1].args[0]
    assert "video/generations/gen_abc/content/video" in download_url
    assert "job_xyz" not in download_url


@pytest.mark.asyncio
async def test_poll_job_failed(azure_service: AzureOpenAIService):
    """A failed job should mark the internal status failed and stop polling."""
    video_id = "vid-2"
    azure_service.video_jobs[video_id] = VideoStatus(
        video_id=video_id, status="queued", progress=10
    )
    poll_resp = _mock_response({"status": "failed"})
    patcher, client = _patch_async_client()
    client.get = AsyncMock(return_value=poll_resp)

    with patcher, patch("asyncio.sleep", new=AsyncMock()):
        await azure_service._poll_job(video_id, "job_f")

    assert azure_service.video_jobs[video_id].status == "failed"
    assert azure_service.video_jobs[video_id].progress == 0


# --------------------------------------------------------------------- queries


def test_get_video_status_existing(azure_service: AzureOpenAIService):
    test_status = VideoStatus(video_id="test-id", status="in_progress", progress=50)
    azure_service.video_jobs["test-id"] = test_status
    result = azure_service.get_video_status("test-id")
    assert result == test_status
    assert result.progress == 50


def test_get_video_status_non_existent(azure_service: AzureOpenAIService):
    assert azure_service.get_video_status("non-existent-id") is None


def test_cleanup_old_jobs(azure_service: AzureOpenAIService):
    for i in range(150):
        job_id = f"job-{i}"
        azure_service.video_jobs[job_id] = VideoStatus(
            video_id=job_id, status="completed", progress=100
        )
    assert len(azure_service.video_jobs) == 150
    azure_service.cleanup_old_jobs()
    assert len(azure_service.video_jobs) == 50
