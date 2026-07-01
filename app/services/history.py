"""History service for tracking video generations."""

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..models import VideoHistoryEntry

logger = logging.getLogger(__name__)


def sanitize_filename(name: str | None) -> str | None:
    """Reduce a user-supplied name to a safe .mp4 download filename, or None."""
    if not name:
        return None
    name = name.strip().replace("/", "_").replace("\\", "_")
    name = re.sub(r"[^A-Za-z0-9 ._-]", "", name).strip(" ._-")
    if not name:
        return None
    if not name.lower().endswith(".mp4"):
        name += ".mp4"
    return name[:120]


class HistoryService:
    """Service for managing video generation history."""

    def __init__(self, storage_dir: str = "/app/data"):
        """Initialize the history service.

        Args:
            storage_dir: Directory to store videos and history data
        """
        self.storage_dir = Path(storage_dir)
        self.videos_dir = self.storage_dir / "videos"
        self.inputs_dir = self.storage_dir / "inputs"
        self.history_file = self.storage_dir / "history.json"

        # Create directories if they don't exist
        try:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            self.videos_dir.mkdir(parents=True, exist_ok=True)
            self.inputs_dir.mkdir(parents=True, exist_ok=True)
            logger.info(
                f"History service initialized - Storage: {self.storage_dir}, Videos: {self.videos_dir}"
            )
        except Exception as e:
            logger.error(f"Failed to create storage directories: {e}")
            raise

        # Load existing history
        self._history: dict[str, dict[str, Any]] = self._load_history()

    def _load_history(self) -> dict[str, dict[str, Any]]:
        """Load history from JSON file."""
        if self.history_file.exists():
            try:
                with open(self.history_file) as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load history file: {e}")
                return {}
        return {}

    def _save_history(self) -> None:
        """Save history to JSON file."""
        try:
            with open(self.history_file, "w") as f:
                json.dump(self._history, f, indent=2, default=str)
            logger.debug(f"History saved to {self.history_file}")
        except Exception as e:
            logger.error(f"Failed to save history: {e}")

    def add_entry(
        self,
        video_id: str,
        prompt: str,
        resolution: str,
        seconds: int,
        had_input_image: bool,
        filename: str | None = None,
        input_path: str | None = None,
    ) -> None:
        """Add a new video generation entry to history.

        Args:
            video_id: Unique video identifier
            prompt: Video generation prompt
            resolution: Video resolution
            seconds: Video duration in seconds
            had_input_image: Whether an input image was provided
            filename: Optional user-chosen download filename
            input_path: Path to the persisted input image (for retries)
        """
        entry = {
            "video_id": video_id,
            "prompt": prompt,
            "resolution": resolution,
            "seconds": seconds,
            "had_input_image": had_input_image,
            "created_at": datetime.now(UTC).isoformat(),
            "completed_at": None,
            "status": "pending",
            "file_path": None,
            "file_size_bytes": None,
            "revised_prompt": None,
            "filename": sanitize_filename(filename),
            "input_path": input_path,
        }
        self._history[video_id] = entry
        self._save_history()
        logger.info(f"Added history entry for video {video_id}")

    def update_entry(
        self,
        video_id: str,
        status: str | None = None,
        file_path: str | None = None,
        file_size_bytes: int | None = None,
        revised_prompt: str | None = None,
    ) -> None:
        """Update an existing history entry.

        Args:
            video_id: Video identifier to update
            status: New status
            file_path: Path to downloaded video file
            file_size_bytes: Size of video file in bytes
            revised_prompt: Revised prompt from Azure
        """
        if video_id not in self._history:
            logger.warning(
                f"Attempted to update non-existent history entry: {video_id}"
            )
            return

        if status:
            self._history[video_id]["status"] = status
            if status == "completed":
                self._history[video_id]["completed_at"] = datetime.now(UTC).isoformat()

        if file_path:
            self._history[video_id]["file_path"] = file_path

        if file_size_bytes is not None:
            self._history[video_id]["file_size_bytes"] = file_size_bytes

        if revised_prompt:
            self._history[video_id]["revised_prompt"] = revised_prompt

        self._save_history()
        logger.info(f"Updated history entry for video {video_id}")

    def reset_entry(self, video_id: str) -> None:
        """Reset an entry to a fresh pending state (for in-place retry)."""
        entry = self._history.get(video_id)
        if entry is None:
            return
        entry["status"] = "pending"
        entry["completed_at"] = None
        entry["file_path"] = None
        entry["file_size_bytes"] = None
        self._save_history()
        logger.info(f"Reset history entry for retry: {video_id}")

    def save_input_image(self, video_id: str, content: bytes) -> str:
        """Persist an input reference image so retries can reuse it."""
        input_path = self.inputs_dir / f"{video_id}.img"
        try:
            with open(input_path, "wb") as f:
                f.write(content)
            return str(input_path)
        except Exception as e:
            logger.error(f"Failed to save input image {video_id}: {e}")
            return ""

    def get_input_image(self, video_id: str) -> bytes | None:
        """Read a persisted input image, or None if not stored."""
        entry = self._history.get(video_id)
        path = None
        if entry and entry.get("input_path"):
            path = Path(entry["input_path"])
        else:
            candidate = self.inputs_dir / f"{video_id}.img"
            if candidate.exists():
                path = candidate
        if path and path.exists():
            try:
                return path.read_bytes()
            except Exception as e:
                logger.error(f"Failed to read input image {video_id}: {e}")
        return None

    def get_entry(self, video_id: str) -> VideoHistoryEntry | None:
        """Get a single history entry by video ID.

        Args:
            video_id: Video identifier

        Returns:
            VideoHistoryEntry or None if not found
        """
        entry_data = self._history.get(video_id)
        if entry_data:
            try:
                return VideoHistoryEntry(**entry_data)
            except Exception as e:
                logger.error(f"Failed to parse history entry {video_id}: {e}")
                return None
        return None

    def get_all_entries(self) -> list[VideoHistoryEntry]:
        """Get all history entries sorted by creation time (newest first).

        Returns:
            List of VideoHistoryEntry objects
        """
        entries = []
        for entry_data in self._history.values():
            try:
                entries.append(VideoHistoryEntry(**entry_data))
            except Exception as e:
                logger.error(f"Failed to parse history entry: {e}")
                continue

        # Sort by created_at, newest first
        entries.sort(key=lambda x: x.created_at, reverse=True)
        return entries

    def get_video_path(self, video_id: str) -> Path | None:
        """Get the file path for a video.

        Args:
            video_id: Video identifier

        Returns:
            Path to video file or None if not found
        """
        entry = self._history.get(video_id)
        if entry and entry.get("file_path"):
            path = Path(entry["file_path"])
            if path.exists():
                return path
        return None

    def get_download_name(self, video_id: str) -> str:
        """Return the user-chosen filename for a video, or a default."""
        entry = self._history.get(video_id)
        if entry and entry.get("filename"):
            return entry["filename"]
        return f"{video_id}.mp4"

    def save_video(self, video_id: str, content: bytes) -> str:
        """Save video content to disk.

        Args:
            video_id: Video identifier
            content: Video file content

        Returns:
            Path to saved video file
        """
        video_path = self.videos_dir / f"{video_id}.mp4"
        try:
            with open(video_path, "wb") as f:
                f.write(content)
            logger.info(
                f"Saved video {video_id} to {video_path} ({len(content)} bytes)"
            )
            return str(video_path)
        except Exception as e:
            logger.error(f"Failed to save video {video_id}: {e}")
            raise

    def delete_entry(self, video_id: str) -> bool:
        """Delete a video and its history entry.

        Args:
            video_id: Video identifier

        Returns:
            True if deleted successfully, False if not found
        """
        if video_id not in self._history:
            logger.warning(f"Attempted to delete non-existent entry: {video_id}")
            return False

        # Delete the video file if it exists
        entry = self._history.get(video_id)
        if entry and entry.get("file_path"):
            video_path = Path(entry["file_path"])
            if video_path.exists():
                try:
                    video_path.unlink()
                    logger.info(f"Deleted video file: {video_path}")
                except Exception as e:
                    logger.error(f"Failed to delete video file {video_path}: {e}")

        # Delete the persisted input image if any
        input_path = self.inputs_dir / f"{video_id}.img"
        if input_path.exists():
            try:
                input_path.unlink()
            except Exception as e:
                logger.error(f"Failed to delete input image {input_path}: {e}")

        # Remove from history
        del self._history[video_id]
        self._save_history()
        logger.info(f"Deleted history entry for video {video_id}")
        return True
