"""Azure OpenAI service for video generation using Sora 2."""

import asyncio
import logging
import os
import uuid
from typing import Any

from openai import AzureOpenAI

from ..models import VideoGenerationRequest, VideoStatus

# Configure logging
logger = logging.getLogger(__name__)


class AzureOpenAIService:
    """Service for interacting with Azure OpenAI Sora 2 API."""

    def __init__(self):
        """Initialize the Azure OpenAI service."""
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")

        # Validate required environment variables
        if not endpoint:
            raise ValueError("AZURE_OPENAI_ENDPOINT environment variable is required")
        if not api_key:
            raise ValueError("AZURE_OPENAI_API_KEY environment variable is required")

        # Ensure endpoint has proper protocol (http:// or https://)
        if not endpoint.startswith(("http://", "https://")):
            raise ValueError(
                "AZURE_OPENAI_ENDPOINT must start with 'http://' or 'https://'. "
                f"Got: {endpoint}"
            )

        # Ensure endpoint ends with /
        if not endpoint.endswith("/"):
            endpoint = f"{endpoint}/"

        # Initialize AzureOpenAI client
        self.client = AzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=api_version,
        )

        # Model deployment name
        self.model = os.getenv("AZURE_OPENAI_DEPLOYMENT", "sora-2")

        # Log configuration (mask API key)
        masked_key = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "***"
        logger.info(
            f"Azure OpenAI Service initialized - "
            f"Endpoint: {endpoint}, API Version: {api_version}, "
            f"Model: {self.model}, API Key: {masked_key}"
        )

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

            logger.info(f"Starting video generation - Video ID: {video_id}")

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
            logger.error(
                f"Error generating video - Video ID: {video_id}, Error type: {type(e).__name__}, Error: {e}"
            )
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

            logger.info(
                f"Calling Sora API with image-to-video - "
                f"Model: {self.model}, Prompt: '{request.prompt}', "
                f"Resolution: {request.resolution.value}, Duration: {request.seconds}s, "
                f"Image size: {len(request.input_image_data)} bytes"
            )
        else:
            logger.info(
                f"Calling Sora API with text-to-video - "
                f"Model: {self.model}, Prompt: '{request.prompt}', "
                f"Resolution: {request.resolution.value}, Duration: {request.seconds}s"
            )

        try:
            # Log the actual API endpoint being called
            logger.debug(
                f"Azure OpenAI API endpoint: {self.client.base_url}, "
                f"API version: {self.client._custom_query['api-version']}"
            )

            response = self.client.videos.create(**api_params)

            # Log successful response
            logger.info(
                f"Sora API response received - "
                f"Video ID: {response.id}, Status: {response.status}, "
                f"Progress: {getattr(response, 'progress', 0)}"
            )

            return {
                "id": response.id,
                "status": response.status,
                "progress": getattr(response, "progress", 0),
            }
        except Exception as e:
            # Log detailed error information
            logger.error(
                f"Sora API call failed - "
                f"Error type: {type(e).__name__}, Error: {str(e)}, "
                f"Model: {self.model}, Prompt: '{request.prompt}'"
            )
            raise

    async def _poll_video_status(self, video_id: str, azure_video_id: str) -> None:
        """Poll Azure API for video completion status."""
        max_polls = 120  # Maximum number of polls (20 minutes at 10s intervals)
        poll_count = 0

        logger.info(
            f"Starting to poll video status - Video ID: {video_id}, Azure Video ID: {azure_video_id}"
        )

        while poll_count < max_polls:
            try:
                # Wait before polling
                await asyncio.sleep(10)
                poll_count += 1

                # Get video status from Azure
                logger.debug(
                    f"Polling video status (attempt {poll_count}/{max_polls}) - Azure Video ID: {azure_video_id}"
                )
                video = self.client.videos.retrieve(azure_video_id)

                # Update job status
                status = video.status
                self.video_jobs[video_id].status = status

                logger.info(
                    f"Video status update - Video ID: {video_id}, Status: {status}, Poll: {poll_count}"
                )

                # Calculate progress based on status
                if status == "queued":
                    self.video_jobs[video_id].progress = 20
                elif status == "in_progress":
                    # Interpolate progress between 20 and 90 based on poll count
                    self.video_jobs[video_id].progress = min(20 + poll_count * 2, 90)
                elif status == "completed":
                    self.video_jobs[video_id].progress = 100
                    logger.info(f"Video generation completed - Video ID: {video_id}")
                    # Download the video
                    try:
                        _ = self.client.videos.download_content(
                            azure_video_id, variant="video"
                        )
                        # For now, we'll store a placeholder URL
                        # In a real scenario, you'd save the content to storage
                        self.video_jobs[video_id].video_url = (
                            f"data:video/mp4;base64,{video_id}"
                        )
                        logger.info(
                            f"Video downloaded successfully - Video ID: {video_id}"
                        )
                    except Exception as e:
                        logger.error(
                            f"Error downloading video - Video ID: {video_id}, Error: {e}"
                        )
                    break
                elif status in ["failed", "cancelled"]:
                    self.video_jobs[video_id].progress = 0
                    logger.error(f"Video generation {status} - Video ID: {video_id}")
                    break

            except Exception as e:
                logger.error(
                    f"Error polling video status - Video ID: {video_id}, Azure Video ID: {azure_video_id}, Error type: {type(e).__name__}, Error: {e}"
                )
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
