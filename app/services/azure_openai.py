"""Azure OpenAI service for video generation using Sora 2.

Talks to the Azure Foundry Sora 2 REST surface directly with httpx:

- Create:   POST {endpoint}/openai/v1/video/generations/jobs?api-version=preview
- Poll:     GET  {endpoint}/openai/v1/video/generations/jobs/{job_id}?api-version=preview
- Download: GET  {endpoint}/openai/v1/video/generations/{generation_id}/content/video
            ?api-version=preview

Authentication is via the ``api-key`` header (API-key mode only).
"""

import asyncio
import json
import logging
import os
import uuid
from typing import Any

import httpx

from ..models import VideoGenerationRequest, VideoStatus
from .history import HistoryService

logger = logging.getLogger(__name__)

# During the Sora 2 preview period the video generation API is served under the
# ``preview`` api-version regardless of the resource's other API versions.
API_VERSION = "preview"

# Map Azure job statuses onto the internal vocabulary used by the frontend,
# the history page CSS, and history.py's completed_at logic. Keeping these
# strings stable means nothing downstream has to change.
_STATUS_MAP = {
    "queued": "queued",
    "preprocessing": "in_progress",
    "running": "in_progress",
    "processing": "in_progress",
    "succeeded": "completed",
    "failed": "failed",
    "cancelled": "cancelled",
}


def _normalize_status(azure_status: str) -> str:
    """Translate an Azure job status into our internal status vocabulary."""
    return _STATUS_MAP.get(azure_status, "in_progress")


class AzureOpenAIService:
    """Service for interacting with the Azure OpenAI Sora 2 REST API."""

    def __init__(self):
        """Initialize the Azure OpenAI service from environment variables."""
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_key = os.getenv("AZURE_OPENAI_API_KEY")

        if not endpoint:
            raise ValueError("AZURE_OPENAI_ENDPOINT environment variable is required")

        if not endpoint.startswith(("http://", "https://")):
            raise ValueError(
                "AZURE_OPENAI_ENDPOINT must start with 'http://' or 'https://'. "
                f"Got: {endpoint}"
            )

        if not api_key:
            raise ValueError("AZURE_OPENAI_API_KEY environment variable is required")

        # Hold the bare resource root; strip any trailing slash or accidental
        # ``/openai...`` path so we always build paths from a clean base.
        endpoint = endpoint.rstrip("/")
        if "/openai" in endpoint:
            endpoint = endpoint.split("/openai", 1)[0]

        self.endpoint = endpoint
        self.api_key = api_key
        self.deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "sora-2")

        masked_key = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "***"
        logger.info(
            "Azure OpenAI Service initialized - "
            f"Endpoint: {self.endpoint}/, API Version: {API_VERSION}, "
            f"Model: {self.deployment}, API Key: {masked_key}"
        )

        self.video_jobs: dict[str, VideoStatus] = {}

        storage_dir = os.getenv("VIDEO_STORAGE_DIR", "/app/data")
        self.history = HistoryService(storage_dir=storage_dir)

    # ------------------------------------------------------------------ URLs

    def _jobs_url(self) -> str:
        return (
            f"{self.endpoint}/openai/v1/video/generations/jobs"
            f"?api-version={API_VERSION}"
        )

    def _job_url(self, job_id: str) -> str:
        return (
            f"{self.endpoint}/openai/v1/video/generations/jobs/{job_id}"
            f"?api-version={API_VERSION}"
        )

    def _download_url(self, generation_id: str) -> str:
        return (
            f"{self.endpoint}/openai/v1/video/generations/{generation_id}"
            f"/content/video?api-version={API_VERSION}"
        )

    def _auth_headers(self, base: dict[str, str] | None = None) -> dict[str, str]:
        headers = dict(base or {})
        headers["api-key"] = self.api_key
        return headers

    # -------------------------------------------------------------- lifecycle

    async def generate_video(self, request: VideoGenerationRequest) -> str:
        """Register a new generation job and kick off the background worker."""
        video_id = str(uuid.uuid4())

        self.video_jobs[video_id] = VideoStatus(
            video_id=video_id, status="pending", progress=0
        )

        self.history.add_entry(
            video_id=video_id,
            prompt=request.prompt,
            resolution=request.resolution.value,
            seconds=request.seconds,
            had_input_image=request.input_image_data is not None,
        )

        asyncio.create_task(self._run_job(request, video_id))

        return video_id

    async def _run_job(self, request: VideoGenerationRequest, video_id: str) -> None:
        """Create the Azure job and poll it to completion in the background."""
        try:
            self.video_jobs[video_id].status = "queued"
            self.video_jobs[video_id].progress = 10
            self.history.update_entry(video_id, status="queued")

            logger.info(f"Starting video generation - Video ID: {video_id}")

            job_id = await self._create_job(request)
            self.video_jobs[video_id].azure_video_id = job_id
            self.video_jobs[video_id].progress = 20

            await self._poll_job(video_id, job_id)
        except Exception as e:
            self.video_jobs[video_id].status = "failed"
            self.video_jobs[video_id].progress = 0
            self.history.update_entry(video_id, status="failed")
            logger.error(
                f"Error generating video - Video ID: {video_id}, "
                f"Error type: {type(e).__name__}, Error: {e}"
            )

    # ------------------------------------------------------------------ create

    async def _create_job(self, request: VideoGenerationRequest) -> str:
        """Create a Sora 2 video generation job. Returns the Azure job id."""
        width, height = (int(v) for v in request.resolution.value.split("x"))

        if request.input_image_data:
            return await self._create_job_multipart(request, width, height)

        body = {
            "prompt": request.prompt,
            "width": width,
            "height": height,
            "n_seconds": request.seconds,
            "model": self.deployment,
        }

        logger.info(
            "Calling Sora API with text-to-video - "
            f"Model: {self.deployment}, Prompt: '{request.prompt}', "
            f"Resolution: {request.resolution.value}, Duration: {request.seconds}s"
        )

        result = await self._post_job(
            json_body=body,
            headers=self._auth_headers({"Content-Type": "application/json"}),
        )
        return result["id"]

    async def _create_job_multipart(
        self, request: VideoGenerationRequest, width: int, height: int
    ) -> str:
        """Create an image-to-video job via multipart inpaint upload."""
        file_name = "input.jpg"
        data = {
            "prompt": request.prompt,
            "width": str(width),
            "height": str(height),
            "n_seconds": str(request.seconds),
            "model": self.deployment,
            "inpaint_items": json.dumps(
                [
                    {
                        "frame_index": 0,
                        "type": "image",
                        "file_name": file_name,
                        "crop_bounds": {
                            "left_fraction": 0.0,
                            "top_fraction": 0.0,
                            "right_fraction": 1.0,
                            "bottom_fraction": 1.0,
                        },
                    }
                ]
            ),
        }
        files = {"files": (file_name, request.input_image_data, "image/jpeg")}

        logger.info(
            "Calling Sora API with image-to-video - "
            f"Model: {self.deployment}, Prompt: '{request.prompt}', "
            f"Resolution: {width}x{height}, Duration: {request.seconds}s, "
            f"Image size: {len(request.input_image_data)} bytes"
        )

        # No explicit Content-Type: httpx sets the multipart boundary.
        result = await self._post_job(
            data=data, files=files, headers=self._auth_headers()
        )
        return result["id"]

    async def _post_job(
        self,
        headers: dict[str, str],
        json_body: dict[str, Any] | None = None,
        data: dict[str, str] | None = None,
        files: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """POST a create-job request and return the parsed JSON body."""
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    self._jobs_url(),
                    headers=headers,
                    json=json_body,
                    data=data,
                    files=files,
                )
                response.raise_for_status()
                result = response.json()
            logger.info(
                "Sora API response received - "
                f"Video ID: {result.get('id')}, Status: {result.get('status')}"
            )
            return result
        except httpx.HTTPStatusError as e:
            logger.error(
                "Sora API HTTP error - "
                f"Status: {e.response.status_code}, Response: {e.response.text}"
            )
            raise Exception(
                f"API request failed with status {e.response.status_code}: "
                f"{e.response.text}"
            ) from e

    # -------------------------------------------------------------------- poll

    async def _poll_job(self, video_id: str, job_id: str) -> None:
        """Poll the Azure job until it reaches a terminal state."""
        max_polls = 120  # ~20 minutes at 10s intervals
        poll_count = 0

        logger.info(
            f"Starting to poll video status - Video ID: {video_id}, Job ID: {job_id}"
        )

        while poll_count < max_polls:
            await asyncio.sleep(10)
            poll_count += 1

            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(
                        self._job_url(job_id), headers=self._auth_headers()
                    )
                    response.raise_for_status()
                    body = response.json()
            except Exception as e:
                logger.error(
                    f"Error polling video status - Video ID: {video_id}, "
                    f"Job ID: {job_id}, Error type: {type(e).__name__}, Error: {e}"
                )
                self.video_jobs[video_id].status = "failed"
                self.video_jobs[video_id].progress = 0
                self.history.update_entry(video_id, status="failed")
                break

            azure_status = body.get("status", "queued")
            status = _normalize_status(azure_status)
            self.video_jobs[video_id].status = status

            logger.info(
                f"Video status update - Video ID: {video_id}, "
                f"Status: {status} ({azure_status}), Poll: {poll_count}"
            )

            if status == "queued":
                self.video_jobs[video_id].progress = 20
            elif status == "in_progress":
                self.video_jobs[video_id].progress = min(20 + poll_count * 2, 90)
            elif status == "completed":
                self.video_jobs[video_id].progress = 100
                logger.info(f"Video generation completed - Video ID: {video_id}")
                await self._download_and_save(video_id, body)
                break
            elif status in ("failed", "cancelled"):
                self.video_jobs[video_id].progress = 0
                self.history.update_entry(video_id, status=status)
                logger.error(f"Video generation {status} - Video ID: {video_id}")
                break

    async def _download_and_save(self, video_id: str, job_body: dict[str, Any]) -> None:
        """Download the finished video and persist it to disk + history."""
        try:
            generations = job_body.get("generations") or []
            if not generations:
                raise ValueError("Job succeeded but returned no generations")

            generation_id = generations[0]["id"]
            self.video_jobs[video_id].azure_generation_id = generation_id

            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.get(
                    self._download_url(generation_id), headers=self._auth_headers()
                )
                response.raise_for_status()
                video_content = response.content

            file_path = self.history.save_video(video_id, video_content)
            file_size = len(video_content)
            self.video_jobs[video_id].video_url = f"/videos/{video_id}"
            self.history.update_entry(
                video_id,
                status="completed",
                file_path=file_path,
                file_size_bytes=file_size,
            )
            logger.info(
                f"Video downloaded and saved - Video ID: {video_id}, "
                f"Generation ID: {generation_id}, Size: {file_size} bytes"
            )
        except Exception as e:
            logger.error(f"Error downloading video - Video ID: {video_id}, Error: {e}")
            self.history.update_entry(video_id, status="completed")

    # ----------------------------------------------------------------- queries

    def get_video_status(self, video_id: str) -> VideoStatus | None:
        """Get the status of a video generation job."""
        return self.video_jobs.get(video_id)

    def cleanup_old_jobs(self, max_jobs: int = 50) -> None:
        """Clean up old video jobs to prevent memory issues."""
        if len(self.video_jobs) > max_jobs:
            sorted_jobs = sorted(self.video_jobs.items(), key=lambda x: x[0])
            jobs_to_keep = dict(sorted_jobs[-max_jobs:])
            self.video_jobs.clear()
            self.video_jobs.update(jobs_to_keep)
