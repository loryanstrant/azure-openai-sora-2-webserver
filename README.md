# Azure OpenAI Sora 2 Video Generator Web Server

A production-ready, containerized web server that connects to Azure OpenAI's Sora 2 model to generate videos. This application provides both a modern web interface and RESTful API endpoints for video generation.

## 🚀 Features

- **Single-page Web Interface**: Video history on the left (file name, download, date,
  prompt), the creation form on the right — no separate history page.
  - 🔍 **Search** history by prompt text
  - 🌗 **Dark mode**: toggle persisted in `localStorage`, follows `prefers-color-scheme`,
    with colour-blind-safe status glyphs (●/◐/○)
  - 🎬 **Modal Playback**: click any completed video to play it full-screen
  - ⬇️ **Download** / 🗑️ **Delete** per entry
- **MCP Server**: the container is also an MCP server (streamable HTTP at `/mcp`), so another
  system can drive **batch** video jobs remotely
- **Persistent Storage**: Videos are downloaded and saved locally with volume mount support
- **Azure OpenAI Integration**: Talks to the Azure Foundry **Sora 2** REST API directly
  (`/openai/v1/video/generations`, api-version `preview`)
- **Containerized**: Multi-stage Docker build optimized for ease of use

## 📋 Requirements

- Python 3.11+
- Docker (for containerized deployment)
- Azure OpenAI account with Sora 2 access
- Azure OpenAI API key and endpoint

## 🔧 Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `AZURE_OPENAI_ENDPOINT` | Your Azure OpenAI **resource** base URL (must start with `http://`/`https://`). Just the resource root — e.g. `https://your-instance.openai.azure.com` or `https://your-instance.cognitiveservices.azure.com`. The app builds the `/openai/v1/video/generations/...` paths itself. | Yes | - |
| `AZURE_OPENAI_API_KEY` | Your Azure OpenAI API key (sent as the `api-key` header) | Yes | - |
| `AZURE_OPENAI_DEPLOYMENT` | Sora 2 model deployment name | No | `sora-2` |
| `MCP_AUTH_TOKEN` | If set, the `/mcp` endpoint requires `Authorization: Bearer <token>`. If unset, `/mcp` is open (intended for LAN / WireGuard-only use). | No | - |
| `VIDEO_STORAGE_DIR` | Directory path for storing generated videos and history | No | `/app/data` |
| `TZ` | Timezone for container logs (e.g., `America/New_York`, `Europe/London`) | No | `UTC` |

### Endpoint configuration

Point `AZURE_OPENAI_ENDPOINT` at your resource root only. Foundry shows several URLs in
different places — **use the base resource URL**, not a pre-built `/openai/...` path. The app
always calls the canonical Sora 2 REST surface (api-version `preview`):

- Create: `POST {endpoint}/openai/v1/video/generations/jobs?api-version=preview`
- Poll:   `GET  {endpoint}/openai/v1/video/generations/jobs/{job_id}?api-version=preview`
- Download: `GET {endpoint}/openai/v1/video/generations/{generation_id}/content/video?api-version=preview`

```bash
export AZURE_OPENAI_ENDPOINT="https://your-instance.openai.azure.com"
export AZURE_OPENAI_API_KEY="your-api-key"
export AZURE_OPENAI_DEPLOYMENT="sora-2"
```

A trailing slash or an accidental `/openai/...` suffix on the endpoint is tolerated and
stripped automatically.

## 🏗️ Installation & Setup

### Docker Deployment

1. **Build the Docker image**
   ```bash
   docker build -t azure-openai-sora-webserver .
   ```

2. **Run the container**

   ```bash
   docker run -d \
     --name sora-webserver \
     -p 8000:8000 \
     -v $(pwd)/data:/app/data \
     -e AZURE_OPENAI_ENDPOINT="https://your-instance.openai.azure.com" \
     -e AZURE_OPENAI_API_KEY="your-api-key" \
     -e AZURE_OPENAI_DEPLOYMENT="sora-2" \
     -e TZ="America/New_York" \
     azure-openai-sora-webserver
   ```

   **Notes**: 
   - The `-v $(pwd)/data:/app/data` mount creates a persistent volume for storing generated videos and history
   - Set `TZ` to your local timezone for accurate log timestamps (e.g., `America/New_York`, `Europe/London`, `Asia/Tokyo`). Defaults to `UTC` if not specified.
   - **Volume Permissions**: The container automatically fixes permissions on mounted volumes. If the mounted directory is owned by root or another user, the container will change ownership to the internal `appuser` at startup. This ensures the application can write videos to the mounted volume without permission errors.

3. **Access the application**
   - Web Interface: http://localhost:8000
   - Health Check: http://localhost:8000/health

### Using Docker Compose

The application is automatically built and published to GitHub Container Registry (GHCR):

```bash
docker pull ghcr.io/loryanstrant/azure-openai-sora-2-webserver:latest
docker run -d \
  --name sora-webserver \
  -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  -e AZURE_OPENAI_ENDPOINT="https://your-instance.openai.azure.com" \
  -e AZURE_OPENAI_API_KEY="your-api-key" \
  -e AZURE_OPENAI_DEPLOYMENT="sora-2" \
  -e TZ="America/New_York" \
  ghcr.io/loryanstrant/azure-openai-sora-2-webserver:latest
```

## 🎯 Usage

### Web Interface

1. Navigate to http://localhost:8000
2. Enter your video description in the prompt field
3. Select resolution (1280x720 landscape or 720x1280 portrait)
4. Set duration (4, 8, or 12 seconds)
5. **(Optional)** Upload a reference image for image-to-video generation
6. Click "Generate Video"
7. Monitor progress and view the generated video
8. Browse, play, download, and delete past videos in the history list on the left of the
   same page. Toggle 🌙/☀️ in the top-right for dark mode.

### MCP Server (batch jobs from another system)

The container also serves an MCP endpoint over streamable HTTP at `/mcp` on the same port,
so another system can run batch jobs. Point an MCP client at `http://<host>:8000/mcp`.

Tools:

| Tool | Purpose |
|------|---------|
| `generate_video(prompt, resolution="1280x720", seconds=4)` | Start a job; returns `video_id` |
| `get_video_status(video_id)` | Status + progress of a job |
| `list_history()` | All past generations (newest first) |
| `get_video(video_id)` | Download URL (`/videos/{video_id}`) for a finished video |

If `MCP_AUTH_TOKEN` is set, every `/mcp` request must send `Authorization: Bearer <token>`.
Example `.mcp.json` entry:

```json
{ "mcpServers": { "sora": {
    "type": "http",
    "url": "http://your-host:8000/mcp",
    "headers": { "Authorization": "Bearer ${MCP_AUTH_TOKEN}" }
} } }
```


## 🐛 Troubleshooting

### Volume Permission Issues

The container runs as root by default, which eliminates most permission issues when mounting volumes. The entrypoint script automatically:
1. Creates necessary directories (`/app/data` and `/app/data/videos`)
2. Ensures directories are accessible and writable
3. Starts the application with full permissions

If you prefer to run the container with a specific user ID (not recommended), you can use:
```bash
docker run -d \
  --user $(id -u):$(id -g) \
  -v /path/to/data:/app/data \
  ...other options...
  azure-openai-sora-webserver
```

**Note**: Running as a non-root user may cause permission issues with mounted volumes.

**Verification**:
Check the container logs to verify startup:
```bash
docker logs your-container-name
```

You should see output like:
```
Directory /app/data exists
Directory /app/data is writable
Starting application as root...
```

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Azure OpenAI for providing Sora 2 video generation capabilities
- FastAPI for the excellent web framework
- The Python community for outstanding tooling and libraries

## 📝 Sora 2 API Notes

This application uses the Azure OpenAI Sora 2 API, which provides the following features:

- **Model**: `sora-2` (configurable via `AZURE_OPENAI_DEPLOYMENT`)
- **Video Durations**: 4, 8, or 12 seconds per generation
- **Resolutions**: 
  - Landscape: 1280x720
  - Portrait: 720x1280
- **Generation Modes**:
  - **Text-to-Video**: Generate videos from text prompts
  - **Image-to-Video**: Animate still images by providing an input reference image
- **Input Image Requirements**:
  - Supported formats: JPEG, PNG, WebP
  - Resolution must match the selected video resolution exactly
  - Used as a visual anchor for the first frame
- **REST surface** (api-version `preview`):
  - `POST /openai/v1/video/generations/jobs` — start a job
  - `GET  /openai/v1/video/generations/jobs/{job_id}` — poll status
  - `GET  /openai/v1/video/generations/{generation_id}/content/video` — download
- **Azure job statuses**: `queued`, `preprocessing`, `running`, `processing`, `succeeded`,
  `failed`, `cancelled` — normalized internally to
  `queued` / `in_progress` / `completed` / `failed` / `cancelled`.

For more information, see the [Microsoft documentation](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/video-generation?pivots=rest-api).
