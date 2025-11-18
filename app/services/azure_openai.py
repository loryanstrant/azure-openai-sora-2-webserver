"""Azure OpenAI service for video generation using Sora 2."""

import asyncio
import logging
import os
import uuid
from typing import Any

import httpx
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
        video_url = os.getenv("AZURE_OPENAI_VIDEO_URL")

        # Validate required environment variables
        if not api_key:
            raise ValueError("AZURE_OPENAI_API_KEY environment variable is required")

        # Store API key and version for use in custom requests
        self.api_key = api_key
        self.api_version = api_version

        # Model deployment name
        self.model = os.getenv("AZURE_OPENAI_DEPLOYMENT", "sora-2")

        # Determine which configuration mode to use
        if video_url:
            # Custom video URL mode - user provides complete URL
            if not video_url.startswith(("http://", "https://")):
                raise ValueError(
                    "AZURE_OPENAI_VIDEO_URL must start with 'http://' or 'https://'. "
                    f"Got: {video_url}"
                )

            # Store the custom video URL for later use
            self.custom_video_url = video_url

            # For custom URL mode, we still need a base endpoint for the client
            # Extract base URL from video URL (everything before /openai/)
            if "/openai/" in video_url:
                endpoint = video_url.split("/openai/")[0] + "/"
            else:
                # If no /openai/ in URL, use the base domain
                from urllib.parse import urlparse

                parsed = urlparse(video_url)
                endpoint = f"{parsed.scheme}://{parsed.netloc}/"

            # Initialize AzureOpenAI client with base endpoint (for polling and download)
            self.client = AzureOpenAI(
                api_key=api_key,
                azure_endpoint=endpoint,
                api_version=api_version,
            )

            # Log configuration (mask API key)
            masked_key = (
                f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "***"
            )
            logger.info(
                f"Azure OpenAI Service initialized with custom video URL - "
                f"Video URL: {video_url}, API Version: {api_version}, "
                f"Model: {self.model}, API Key: {masked_key}"
            )
        else:
            # Legacy mode - construct URL from endpoint
            if not endpoint:
                raise ValueError(
                    "AZURE_OPENAI_ENDPOINT environment variable is required"
                )

            # Ensure endpoint has proper protocol (http:// or https://)
            if not endpoint.startswith(("http://", "https://")):
                raise ValueError(
                    "AZURE_OPENAI_ENDPOINT must start with 'http://' or 'https://'. "
                    f"Got: {endpoint}"
                )

            # Ensure endpoint ends with /
            if not endpoint.endswith("/"):
                endpoint = f"{endpoint}/"

            # For Azure OpenAI, we need to include the deployment in the endpoint URL
            # The SDK expects: https://{endpoint}/openai/deployments/{deployment}/
            if "/openai/" not in endpoint:
                # Add /openai/ if not present
                endpoint = f"{endpoint}openai/"

            # Add deployments path if not already present
            if "/deployments/" not in endpoint:
                endpoint = f"{endpoint}deployments/{self.model}/"

            # Initialize AzureOpenAI client
            self.client = AzureOpenAI(
                api_key=api_key,
                azure_endpoint=endpoint,
                api_version=api_version,
            )

            # No custom video URL in legacy mode
            self.custom_video_url = None

            # Log configuration (mask API key)
            masked_key = (
                f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "***"
            )
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
        if self.custom_video_url:
            # Use custom URL with direct HTTP call
            return self._call_sora_api_custom_url(request)
        else:
            # Use OpenAI SDK
            return self._call_sora_api_sdk(request)

    def _call_sora_api_custom_url(
        self, request: VideoGenerationRequest
    ) -> dict[str, Any]:
        """Call the Sora 2 API using custom video URL with direct HTTP request."""
        # Prepare request body
        request_body = {
            "model": self.model,
            "prompt": request.prompt,
            "size": request.resolution.value,
            "seconds": str(request.seconds),
        }

        # Prepare headers
        headers = {
            "Content-Type": "application/json",
            "api-key": self.api_key,
        }

        logger.info(
            f"Calling Sora API with custom URL - "
            f"URL: {self.custom_video_url}, Model: {self.model}, "
            f"Prompt: '{request.prompt}', Resolution: {request.resolution.value}, "
            f"Duration: {request.seconds}s"
        )

        try:
            # Make HTTP POST request
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    self.custom_video_url,
                    json=request_body,
                    headers=headers,
                )
                response.raise_for_status()
                result = response.json()

            # Log successful response
            logger.info(
                f"Sora API response received - "
                f"Video ID: {result.get('id')}, Status: {result.get('status')}"
            )

            return {
                "id": result.get("id"),
                "status": result.get("status", "queued"),
                "progress": result.get("progress", 0),
            }
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Sora API HTTP error - "
                f"Status: {e.response.status_code}, Response: {e.response.text}"
            )
            raise Exception(
                f"API request failed with status {e.response.status_code}: {e.response.text}"
            ) from e
        except Exception as e:
            logger.error(
                f"Sora API call failed - "
                f"Error type: {type(e).__name__}, Error: {str(e)}"
            )
            raise

    def _call_sora_api_sdk(self, request: VideoGenerationRequest) -> dict[str, Any]:
        """Call the Sora 2 API using OpenAI SDK."""
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

                if self.custom_video_url:
                    # Use custom URL with direct HTTP call
                    status_url = f"{self.custom_video_url}/{azure_video_id}"
                    headers = {"api-key": self.api_key}

                    async with httpx.AsyncClient(timeout=30.0) as client:
                        response = await client.get(status_url, headers=headers)
                        response.raise_for_status()
                        video_data = response.json()

                    status = video_data.get("status", "queued")
                else:
                    # Use SDK
                    video = self.client.videos.retrieve(azure_video_id)
                    status = video.status

                # Update job status
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
                        if self.custom_video_url:
                            # For custom URL, we would need a download endpoint
                            # For now, store a placeholder
                            self.video_jobs[video_id].video_url = (
                                f"data:video/mp4;base64,{video_id}"
                            )
                        else:
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
