"""FastAPI application for Azure OpenAI Sora video generation."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .models import VideoGenerationRequest, VideoResolution, VideoStatus
from .services.azure_openai import AzureOpenAIService

# Application version
__version__ = "1.0.0"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Global service instance
azure_service = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup and shutdown."""
    # Startup
    global azure_service
    azure_service = AzureOpenAIService()
    logger.info(f"Starting Azure OpenAI Sora Web Server v{__version__}...")
    print("Starting Azure OpenAI Sora Web Server...")

    yield

    # Shutdown
    logger.info("Shutting down Azure OpenAI Sora Web Server...")
    print("Shutting down Azure OpenAI Sora Web Server...")
    # Clean up any pending tasks
    if azure_service:
        azure_service.cleanup_old_jobs()
    logger.info("Cleanup completed.")
    print("Cleanup completed.")


# Create FastAPI app with lifespan handler
app = FastAPI(
    title="Azure OpenAI Sora Video Generator",
    description="A web server for generating videos using Azure OpenAI Sora",
    version=__version__,
    lifespan=lifespan,
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    """Serve the main web interface."""
    return FileResponse("static/index.html")


@app.post("/generate", response_model=dict)
async def generate_video(
    prompt: str = Form(...),
    resolution: str = Form(default="1280x720"),
    seconds: int = Form(default=4),
    input_image: UploadFile | str | None = File(default=None),
):
    """Generate a video using Azure OpenAI Sora.

    Args:
        prompt: Video description prompt
        resolution: Video resolution (1280x720 or 720x1280)
        seconds: Video duration in seconds (4, 8, or 12)
        input_image: Optional input reference image for image-to-video generation
    """
    try:
        # Validate and convert resolution
        try:
            resolution_enum = VideoResolution(resolution)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid resolution. Must be one of: {', '.join([r.value for r in VideoResolution])}",
            ) from None

        # Read image data if provided
        image_data = None
        if input_image and not isinstance(input_image, str):
            # If input_image is a string (empty filename from browser), treat as no file
            # Only process if it's an actual UploadFile
            if input_image.filename:
                # Validate file type
                content_type = input_image.content_type
                if content_type not in ["image/jpeg", "image/png", "image/webp"]:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Invalid image type: {content_type}. Must be JPEG, PNG, or WebP",
                    )

                # Read the image data
                image_data = await input_image.read()

        # Create request object with validation
        try:
            request = VideoGenerationRequest(
                prompt=prompt,
                resolution=resolution_enum,
                seconds=seconds,
                input_image_data=image_data,
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e

        video_id = await azure_service.generate_video(request)
        return {"video_id": video_id, "status": "pending"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/status/{video_id}", response_model=VideoStatus)
async def get_video_status(video_id: str):
    """Get the status of a video generation job."""
    status = azure_service.get_video_status(video_id)
    if not status:
        raise HTTPException(status_code=404, detail="Video job not found")
    return status


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "azure-openai-sora", "version": __version__}


@app.get("/version")
async def version():
    """Get application version."""
    return {"version": __version__}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
