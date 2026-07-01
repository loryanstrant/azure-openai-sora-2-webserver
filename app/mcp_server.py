"""MCP server exposing Sora 2 video generation for remote / batch use.

Mounted inside the FastAPI app (see ``app/main.py``) at ``/mcp`` using the
streamable-HTTP transport, so the same container is both a web app and an MCP
endpoint. Another system can call ``generate_video`` in a loop to run batch
jobs, then poll ``get_video_status`` / fetch results via ``get_video``.

The tools delegate to the shared :class:`AzureOpenAIService` singleton, which
is injected by the app lifespan via :func:`set_azure_service` (it doesn't exist
at import time, so it can't be imported directly).
"""

import os

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .models import VideoGenerationRequest, VideoResolution

# Injected by the FastAPI lifespan once the service singleton exists.
_service = None


def set_azure_service(service) -> None:
    """Register the shared AzureOpenAIService singleton for the MCP tools."""
    global _service
    _service = service


def _svc():
    if _service is None:
        raise RuntimeError("Azure service not initialized")
    return _service


# The MCP SDK's DNS-rebinding protection only allows localhost Host headers by
# default, which 421s remote/LAN callers. This server is deployed LAN/VPN-only
# (and optionally gated by MCP_AUTH_TOKEN), so disable that host check to let
# other systems drive batch jobs. Restrict to specific hosts via
# MCP_ALLOWED_HOSTS (comma-separated) if you'd rather not disable it.
_allowed_hosts = [
    h.strip() for h in os.getenv("MCP_ALLOWED_HOSTS", "").split(",") if h.strip()
]
if _allowed_hosts:
    _security = TransportSecuritySettings(allowed_hosts=_allowed_hosts)
else:
    _security = TransportSecuritySettings(enable_dns_rebinding_protection=False)

# streamable_http_path="/" so that, when mounted at "/mcp" by the FastAPI app,
# the endpoint is reachable at "/mcp/" instead of "/mcp/mcp".
mcp = FastMCP(
    "azure-sora",
    stateless_http=True,
    streamable_http_path="/",
    transport_security=_security,
)


@mcp.tool()
async def generate_video(
    prompt: str,
    resolution: str = "1280x720",
    seconds: int = 4,
    filename: str = "",
) -> dict:
    """Start a Sora 2 video generation job.

    Args:
        prompt: Description of the video to generate.
        resolution: "1280x720" (landscape) or "720x1280" (portrait).
        seconds: Duration in seconds (4, 8, or 12).
        filename: Optional download filename for the finished video.

    Returns a dict with the ``video_id`` to poll with ``get_video_status``.
    """
    resolution_enum = VideoResolution(resolution)
    request = VideoGenerationRequest(
        prompt=prompt, resolution=resolution_enum, seconds=seconds
    )
    video_id = await _svc().generate_video(request, filename=filename or None)
    return {"video_id": video_id, "status": "pending"}


@mcp.tool()
def get_video_status(video_id: str) -> dict:
    """Get the status and progress of a video generation job."""
    status = _svc().get_video_status(video_id)
    if status is None:
        return {"error": "not_found", "video_id": video_id}
    return status.model_dump(mode="json")


@mcp.tool()
def list_history() -> list[dict]:
    """List all past video generations, newest first."""
    return [e.model_dump(mode="json") for e in _svc().history.get_all_entries()]


@mcp.tool()
def get_video(video_id: str) -> dict:
    """Get the download URL (relative to this server) for a finished video.

    The URL is served by the same container at ``/videos/{video_id}``.
    """
    status = _svc().get_video_status(video_id)
    path = _svc().history.get_video_path(video_id)
    return {
        "video_id": video_id,
        "video_url": f"/videos/{video_id}" if path else None,
        "available": path is not None,
        "status": status.status if status else None,
    }


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """Reject requests lacking a matching ``Authorization: Bearer`` token."""

    def __init__(self, app, token: str):
        super().__init__(app)
        self._token = token

    async def dispatch(self, request: Request, call_next):
        if request.headers.get("Authorization", "") != f"Bearer {self._token}":
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)


def build_mcp_app():
    """Build the streamable-HTTP ASGI app, optionally guarded by a bearer token.

    If ``MCP_AUTH_TOKEN`` is set, every request must present it; if unset, the
    endpoint is open (intended for LAN / WireGuard-only deployment).
    """
    app = mcp.streamable_http_app()
    token = os.getenv("MCP_AUTH_TOKEN")
    if token:
        app.add_middleware(BearerAuthMiddleware, token=token)
    return app
