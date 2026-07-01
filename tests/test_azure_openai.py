"""Tests for the Azure OpenAI Sora 2 service (OpenAI-compatible /videos API)."""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.models import VideoGenerationRequest, VideoResolution, VideoStatus
from app.services.azure_openai import AzureOpenAIService, _normalize_status


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
    """Patch httpx.AsyncClient with mocked post/get and return the CM + client."""
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
    """Trailing slash / /videos / /openai path should be stripped from the base."""
    assert azure_service.endpoint == "https://test.openai.azure.com"
    assert (
        azure_service._videos_url() == "https://test.openai.azure.com/openai/v1/videos"
    )


def test_endpoint_strips_videos_suffix(mock_env_vars):
    """A pasted .../videos URL should be reduced to the resource base."""
    with patch.dict(
        "os.environ",
        {"AZURE_OPENAI_ENDPOINT": "https://foo.services.ai.azure.com/openai/v1/videos"},
    ):
        svc = AzureOpenAIService()
    assert svc.endpoint == "https://foo.services.ai.azure.com"
    assert svc._videos_url() == "https://foo.services.ai.azure.com/openai/v1/videos"


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
async def test_create_video_builds_correct_body(azure_service: AzureOpenAIService):
    """Text-to-video POST must target /videos with size/seconds + Bearer auth."""
    request = VideoGenerationRequest(
        prompt="A beautiful sunset",
        resolution=VideoResolution.PORTRAIT,
        seconds=8,
    )
    post_resp = _mock_response({"id": "video_123", "status": "queued"})
    patcher, client = _patch_async_client(post=post_resp)

    with patcher:
        remote_id = await azure_service._create_video(request)

    assert remote_id == "video_123"
    args, kwargs = client.post.call_args
    assert args[0] == "https://test.openai.azure.com/openai/v1/videos"
    assert kwargs["json"] == {
        "prompt": "A beautiful sunset",
        "model": "sora-2",
        "size": "720x1280",
        "seconds": "8",
    }
    assert kwargs["headers"]["Authorization"] == "Bearer test-api-key"


@pytest.mark.asyncio
async def test_create_video_multipart_when_image(azure_service: AzureOpenAIService):
    """Image-to-video must send multipart input_reference and no Content-Type."""
    request = VideoGenerationRequest(
        prompt="animate this",
        resolution=VideoResolution.LANDSCAPE,
        seconds=4,
        input_image_data=b"fake_image_bytes",
    )
    post_resp = _mock_response({"id": "video_img", "status": "queued"})
    patcher, client = _patch_async_client(post=post_resp)

    with patcher:
        remote_id = await azure_service._create_video(request)

    assert remote_id == "video_img"
    kwargs = client.post.call_args.kwargs
    assert kwargs["files"]["input_reference"][1] == b"fake_image_bytes"
    assert kwargs["data"]["size"] == "1280x720"
    assert kwargs["data"]["seconds"] == "4"
    assert "Content-Type" not in kwargs["headers"]
    assert kwargs["headers"]["Authorization"] == "Bearer test-api-key"


@pytest.mark.asyncio
async def test_create_video_http_error(azure_service: AzureOpenAIService):
    """A non-2xx create response should raise with the status + body."""
    request = VideoGenerationRequest(
        prompt="boom", resolution=VideoResolution.LANDSCAPE, seconds=4
    )
    err_resp = MagicMock()
    err_resp.status_code = 404
    err_resp.text = "not found"
    err_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "404", request=MagicMock(), response=err_resp
    )
    patcher, _ = _patch_async_client(post=err_resp)

    with patcher, pytest.raises(Exception, match="404"):
        await azure_service._create_video(request)


# --------------------------------------------------------------------- status


@pytest.mark.parametrize(
    "provider_status,expected",
    [
        ("queued", "queued"),
        ("preprocessing", "in_progress"),
        ("running", "in_progress"),
        ("in_progress", "in_progress"),
        ("succeeded", "completed"),
        ("completed", "completed"),
        ("failed", "failed"),
        ("cancelled", "cancelled"),
        ("something_new", "in_progress"),
    ],
)
def test_status_normalization(provider_status, expected):
    assert _normalize_status(provider_status) == expected


@pytest.mark.asyncio
async def test_poll_video_success_downloads(azure_service: AzureOpenAIService):
    """On completed, poll must download /videos/{id}/content for the same id."""
    video_id = "vid-1"
    azure_service.video_jobs[video_id] = VideoStatus(
        video_id=video_id, status="queued", progress=10
    )

    poll_resp = _mock_response({"status": "completed", "progress": 100})
    download_resp = _mock_response(content=b"MP4DATA")
    patcher, client = _patch_async_client()
    # First GET = poll, second GET = download.
    client.get = AsyncMock(side_effect=[poll_resp, download_resp])

    with patcher, patch("asyncio.sleep", new=AsyncMock()):
        await azure_service._poll_video(video_id, "video_abc")

    status = azure_service.video_jobs[video_id]
    assert status.status == "completed"
    assert status.progress == 100
    poll_url = client.get.call_args_list[0].args[0]
    download_url = client.get.call_args_list[-1].args[0]
    assert poll_url == "https://test.openai.azure.com/openai/v1/videos/video_abc"
    assert (
        download_url
        == "https://test.openai.azure.com/openai/v1/videos/video_abc/content"
    )


@pytest.mark.asyncio
async def test_poll_video_failed(azure_service: AzureOpenAIService):
    """A failed video should mark the internal status failed and stop polling."""
    video_id = "vid-2"
    azure_service.video_jobs[video_id] = VideoStatus(
        video_id=video_id, status="queued", progress=10
    )
    poll_resp = _mock_response({"status": "failed"})
    patcher, client = _patch_async_client()
    client.get = AsyncMock(return_value=poll_resp)

    with patcher, patch("asyncio.sleep", new=AsyncMock()):
        await azure_service._poll_video(video_id, "video_f")

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


# ------------------------------------------------------------- queue / retry


@pytest.mark.asyncio
async def test_generate_video_enqueues(azure_service: AzureOpenAIService):
    """generate_video should enqueue a job (bounded worker pool), not run it."""
    request = VideoGenerationRequest(
        prompt="q", resolution=VideoResolution.LANDSCAPE, seconds=4
    )
    with patch.object(azure_service, "_ensure_workers"):
        video_id = await azure_service.generate_video(request)
    assert azure_service.video_jobs[video_id].status == "pending"
    assert azure_service._queue.qsize() == 1


@pytest.mark.asyncio
async def test_retry_video_resets_and_reenqueues(azure_service: AzureOpenAIService):
    azure_service.history.add_entry("vid-r", "p", "1280x720", 4, False)
    azure_service.history.update_entry(
        "vid-r", status="completed", file_path="/x.mp4", file_size_bytes=9
    )
    with patch.object(azure_service, "_ensure_workers"):
        ok = await azure_service.retry_video("vid-r")
    assert ok is True
    assert azure_service.video_jobs["vid-r"].status == "pending"
    entry = azure_service.history.get_entry("vid-r")
    assert entry.status == "pending" and entry.file_path is None
    assert azure_service._queue.qsize() == 1


@pytest.mark.asyncio
async def test_retry_video_unknown(azure_service: AzureOpenAIService):
    with patch.object(azure_service, "_ensure_workers"):
        assert await azure_service.retry_video("nope") is False


@pytest.mark.asyncio
async def test_post_video_retries_on_429(azure_service: AzureOpenAIService):
    """A 429 should back off and retry, then succeed."""
    request = VideoGenerationRequest(
        prompt="x", resolution=VideoResolution.LANDSCAPE, seconds=4
    )
    resp429 = MagicMock()
    resp429.status_code = 429
    resp429.headers = {}
    resp429.text = "rate limited"
    resp429.raise_for_status.side_effect = httpx.HTTPStatusError(
        "429", request=MagicMock(), response=resp429
    )
    ok = _mock_response({"id": "video_ok", "status": "queued"})

    client = MagicMock()
    client.post = AsyncMock(side_effect=[resp429, ok])
    async_cm = MagicMock()
    async_cm.__aenter__ = AsyncMock(return_value=client)
    async_cm.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("httpx.AsyncClient", return_value=async_cm),
        patch("asyncio.sleep", new=AsyncMock()),
    ):
        remote_id = await azure_service._create_video(request)

    assert remote_id == "video_ok"
    assert client.post.call_count == 2
