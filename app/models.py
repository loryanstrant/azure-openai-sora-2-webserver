"""Data models for the Azure OpenAI Sora service."""

from enum import Enum

from pydantic import BaseModel, Field, field_validator


class VideoResolution(str, Enum):
    """Video resolution options for Sora 2."""

    PORTRAIT = "720x1280"  # Portrait format
    LANDSCAPE = "1280x720"  # Landscape format


class VideoGenerationRequest(BaseModel):
    """Request model for video generation."""

    prompt: str = Field(
        ..., min_length=1, max_length=1000, description="Video description prompt"
    )
    resolution: VideoResolution = Field(
        default=VideoResolution.LANDSCAPE, description="Video resolution"
    )
    seconds: int = Field(
        default=4, description="Video duration in seconds (4, 8, or 12)"
    )

    @field_validator("seconds")
    @classmethod
    def validate_seconds(cls, v: int) -> int:
        """Validate that seconds is one of the allowed values."""
        if v not in [4, 8, 12]:
            raise ValueError("seconds must be 4, 8, or 12")
        return v

    @property
    def duration(self) -> int:
        """Backward compatibility property for duration."""
        return self.seconds


class VideoStatus(BaseModel):
    """Status model for video generation jobs."""

    video_id: str
    status: str
    progress: int = Field(default=0, ge=0, le=100)
    video_url: str | None = None
    revised_prompt: str | None = None
    azure_video_id: str | None = None  # The video ID from Azure API
