"""Azure OpenAI service for video generation using Sora 2."""

import asyncio
import os
import uuid
from typing import Any

from openai import OpenAI

from ..models import VideoGenerationRequest, VideoStatus


class AzureOpenAIService:
    """Service for interacting with Azure OpenAI Sora 2 API."""

    def __init__(self):
        """Initialize the Azure OpenAI service."""
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_key = os.getenv("AZURE_OPENAI_API_KEY")

        # Ensure endpoint ends with /
        if endpoint and not endpoint.endswith("/"):
            endpoint = f"{endpoint}/"

        # Initialize OpenAI client with Azure endpoint
        self.client = OpenAI(
            api_key=api_key,
            base_url=f"{endpoint}openai/v1/",
            default_headers={"api-key": api_key} if api_key else None,
        )

        # Model deployment name
        self.model = os.getenv("AZURE_OPENAI_DEPLOYMENT", "sora-2")

        self.video_jobs: dict[str, VideoStatus] = {}

    async def generate_video(self, request: VideoGenerationRequest) -> str:
        """Generate a video asynchronously."""
        video_id = str(uuid.uuid4())

        # Create initial job status
        self.video_jobs[video_id] = VideoStatus(
            video_id=video_id, status="pending", progress=0
        )

        # Start async generation
        asyncio.create_task(self._generate_video_async(request, video_id))

        return video_id

    async def _generate_video_async(
        self, request: VideoGenerationRequest, video_id: str
    ) -> None:
        """Generate video asynchronously in background."""
        try:
            # Update status to processing
            self.video_jobs[video_id].status = "queued"
            self.video_jobs[video_id].progress = 10

            # Call Sora 2 API
            video_response = self._call_sora_api(request)

            # Store the video ID from Azure
            self.video_jobs[video_id].azure_video_id = video_response.get("id")
            self.video_jobs[video_id].status = video_response.get("status", "queued")
            self.video_jobs[video_id].progress = 20

            # Poll for completion
            await self._poll_video_status(video_id, video_response.get("id"))

        except Exception as e:
            self.video_jobs[video_id].status = "failed"
            self.video_jobs[video_id].progress = 0
            print(f"Error generating video: {e}")
            raise e

    def _call_sora_api(self, request: VideoGenerationRequest) -> dict[str, Any]:
        """Call the Sora 2 API for video generation."""
        # Prepare API call parameters
        api_params = {
            "model": self.model,
            "prompt": request.prompt,
            "size": request.resolution.value,
            "seconds": str(request.seconds),
        }

        # Add input_reference if provided
        if request.input_image_data:
            import io

            # Create a file-like object from the image data
            image_file = io.BytesIO(request.input_image_data)
            api_params["input_reference"] = image_file

        response = self.client.videos.create(**api_params)

        return {
            "id": response.id,
            "status": response.status,
            "progress": getattr(response, "progress", 0),
        }

    async def _poll_video_status(self, video_id: str, azure_video_id: str) -> None:
        """Poll Azure API for video completion status."""
        max_polls = 120  # Maximum number of polls (20 minutes at 10s intervals)
        poll_count = 0

        while poll_count < max_polls:
            try:
                # Wait before polling
                await asyncio.sleep(10)
                poll_count += 1

                # Get video status from Azure
                video = self.client.videos.retrieve(azure_video_id)

                # Update job status
                status = video.status
                self.video_jobs[video_id].status = status

                # Calculate progress based on status
                if status == "queued":
                    self.video_jobs[video_id].progress = 20
                elif status == "in_progress":
                    # Interpolate progress between 20 and 90 based on poll count
                    self.video_jobs[video_id].progress = min(20 + poll_count * 2, 90)
                elif status == "completed":
                    self.video_jobs[video_id].progress = 100
                    # Download the video
                    try:
                        _ = self.client.videos.download_content(
                            azure_video_id, variant="video"
                        )
                        # For now, we'll store a placeholder URL
                        # In a real scenario, you'd save the content to storage
                        self.video_jobs[video_id].video_url = f"data:video/mp4;base64,{video_id}"
                    except Exception as e:
                        print(f"Error downloading video: {e}")
                    break
                elif status in ["failed", "cancelled"]:
                    self.video_jobs[video_id].progress = 0
                    break

            except Exception as e:
                print(f"Error polling video status: {e}")
                self.video_jobs[video_id].status = "failed"
                self.video_jobs[video_id].progress = 0
                break

    def get_video_status(self, video_id: str) -> VideoStatus | None:
        """Get the status of a video generation job."""
        return self.video_jobs.get(video_id)

    def cleanup_old_jobs(self, max_jobs: int = 50) -> None:
        """Clean up old video jobs to prevent memory issues."""
        if len(self.video_jobs) > max_jobs:
            # Keep only the most recent jobs
            sorted_jobs = sorted(self.video_jobs.items(), key=lambda x: x[0])
            jobs_to_keep = dict(sorted_jobs[-max_jobs:])
            self.video_jobs.clear()
            self.video_jobs.update(jobs_to_keep)
