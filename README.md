# Azure OpenAI Sora 2 Video Generator Web Server

A production-ready, containerized web server that connects to Azure OpenAI's Sora 2 model to generate videos. This application provides both a modern web interface and RESTful API endpoints for video generation.

## 🚀 Features

- **Modern FastAPI Web Server**: Built with FastAPI using modern async patterns and lifespan handlers
- **Web Interface**: Intuitive HTML/CSS/JavaScript frontend for easy video generation
- **Enhanced Video History**: Advanced history page with search, filtering, sorting, and modal video playback
  - 🔍 **Search**: Filter videos by prompt text
  - 📊 **Sort**: Sort by date, resolution, or duration
  - 🎯 **Filter**: Filter by resolution, duration, and status
  - 🎬 **Modal Playback**: Click any video to view in a full-screen modal
  - 🗑️ **Delete**: Remove videos and their history entries
- **Persistent Storage**: Videos are downloaded and saved locally with volume mount support
- **RESTful API**: Complete API with automatic documentation via FastAPI
- **Azure OpenAI Integration**: Seamless connection to Azure OpenAI Sora 2 video generation
- **Containerized**: Multi-stage Docker build optimized for ease of use
- **Comprehensive Testing**: Unit, integration, and API tests with mocking
- **Code Quality**: Linting, formatting, and type checking with Ruff and Black
- **CI/CD Pipeline**: GitHub Actions workflow with automated testing and deployment
- **Health Monitoring**: Built-in health checks and logging

## 📋 Requirements

- Python 3.11+
- Docker (for containerized deployment)
- Azure OpenAI account with Sora 2 access
- Azure OpenAI API key and endpoint

## 🔧 Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `AZURE_OPENAI_API_KEY` | Your Azure OpenAI API key | Yes | - |
| `AZURE_OPENAI_VIDEO_URL` | **(Recommended)** Complete URL for video generation endpoint. When provided, this takes precedence over other URL configuration. Use this to specify the exact endpoint URL for your Azure service. Example: `https://your-instance.cognitiveservices.azure.com/openai/v1/videos` | No | - |
| `AZURE_OPENAI_ENDPOINT` | Your Azure OpenAI endpoint URL (must start with `http://` or `https://`). Only used if `AZURE_OPENAI_VIDEO_URL` is not set. | Yes (if `AZURE_OPENAI_VIDEO_URL` not set) | - |
| `AZURE_OPENAI_DEPLOYMENT` | Sora 2 model deployment name | No | `sora-2` |
| `AZURE_OPENAI_API_VERSION` | Azure OpenAI API version for video generation. Only used if `AZURE_OPENAI_VIDEO_URL` is not set. | No | `2024-08-01-preview` |
| `VIDEO_STORAGE_DIR` | Directory path for storing generated videos and history | No | `/app/data` |
| `TZ` | Timezone for container logs (e.g., `America/New_York`, `Europe/London`) | No | `UTC` |

### Configuration Modes

The service supports two configuration modes:

#### 1. Custom Video URL Mode (Recommended)
Use `AZURE_OPENAI_VIDEO_URL` to specify the complete endpoint URL. This is the most flexible approach and works with different Azure services and URL structures:

```bash
export AZURE_OPENAI_API_KEY="your-api-key"
export AZURE_OPENAI_VIDEO_URL="https://your-instance.cognitiveservices.azure.com/openai/v1/videos"
export AZURE_OPENAI_DEPLOYMENT="sora-2"
```

This mode is recommended because:
- It gives you full control over the endpoint URL
- It works with both `.openai.azure.com` and `.cognitiveservices.azure.com` domains
- It supports different API path structures
- It allows you to omit API versions if not required by your service

#### 2. Legacy Mode (Automatic URL Construction)
Use `AZURE_OPENAI_ENDPOINT` to let the service construct the URL automatically:

```bash
export AZURE_OPENAI_API_KEY="your-api-key"
export AZURE_OPENAI_ENDPOINT="https://your-instance.openai.azure.com/"
export AZURE_OPENAI_DEPLOYMENT="sora-2"
export AZURE_OPENAI_API_VERSION="2024-08-01-preview"
```

This mode automatically constructs URLs in the format:
`{ENDPOINT}/openai/deployments/{DEPLOYMENT}/videos?api-version={API_VERSION}`

## 🏗️ Installation & Setup

### Local Development

1. **Clone the repository**
   ```bash
   git clone https://github.com/loryanstrant/Azure-OpenAI-Sora-webserver.git
   cd Azure-OpenAI-Sora-webserver
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set environment variables**

   **Option A: Using Custom Video URL (Recommended)**
   ```bash
   export AZURE_OPENAI_API_KEY="your-api-key"
   export AZURE_OPENAI_VIDEO_URL="https://your-instance.cognitiveservices.azure.com/openai/v1/videos"
   export AZURE_OPENAI_DEPLOYMENT="sora-2"
   ```

   **Option B: Using Legacy Endpoint Configuration**
   ```bash
   export AZURE_OPENAI_API_KEY="your-api-key"
   export AZURE_OPENAI_ENDPOINT="https://your-instance.openai.azure.com/"
   export AZURE_OPENAI_DEPLOYMENT="sora-2"
   ```

4. **Run the application**
   ```bash
   python -m app.main
   ```

5. **Access the application**
   - Web Interface: http://localhost:8000
   - API Documentation: http://localhost:8000/docs
   - Health Check: http://localhost:8000/health

### Docker Deployment

1. **Build the Docker image**
   ```bash
   docker build -t azure-openai-sora-webserver .
   ```

2. **Run the container**

   **Option A: Using Custom Video URL (Recommended)**
   ```bash
   docker run -d \
     --name sora-webserver \
     -p 8000:8000 \
     -v $(pwd)/data:/app/data \
     -e AZURE_OPENAI_API_KEY="your-api-key" \
     -e AZURE_OPENAI_VIDEO_URL="https://your-instance.cognitiveservices.azure.com/openai/v1/videos" \
     -e TZ="America/New_York" \
     azure-openai-sora-webserver
   ```

   **Option B: Using Legacy Endpoint Configuration**
   ```bash
   docker run -d \
     --name sora-webserver \
     -p 8000:8000 \
     -v $(pwd)/data:/app/data \
     -e AZURE_OPENAI_API_KEY="your-api-key" \
     -e AZURE_OPENAI_ENDPOINT="https://your-instance.openai.azure.com/" \
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

### Using GitHub Container Registry

The application is automatically built and published to GitHub Container Registry (GHCR):

**Option A: Using Custom Video URL (Recommended)**
```bash
docker pull ghcr.io/loryanstrant/azure-openai-sora-webserver:latest
docker run -d \
  --name sora-webserver \
  -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  -e AZURE_OPENAI_API_KEY="your-api-key" \
  -e AZURE_OPENAI_VIDEO_URL="https://your-instance.cognitiveservices.azure.com/openai/v1/videos" \
  -e TZ="America/New_York" \
  ghcr.io/loryanstrant/azure-openai-sora-webserver:latest
```

**Option B: Using Legacy Endpoint Configuration**
```bash
docker pull ghcr.io/loryanstrant/azure-openai-sora-webserver:latest
docker run -d \
  --name sora-webserver \
  -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  -e AZURE_OPENAI_API_KEY="your-api-key" \
  -e AZURE_OPENAI_ENDPOINT="https://your-instance.openai.azure.com/" \
  -e TZ="America/New_York" \
  ghcr.io/loryanstrant/azure-openai-sora-webserver:latest
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
8. View all generated videos at http://localhost:8000/static/history.html

### API Endpoints

#### Generate Video (Text-to-Video)
```bash
POST /generate
Content-Type: multipart/form-data

prompt: "A beautiful sunset over the ocean"
resolution: "1280x720"
seconds: 4
```

#### Generate Video (Image-to-Video)
```bash
POST /generate
Content-Type: multipart/form-data

prompt: "Continue this scene with smooth motion"
resolution: "1280x720"
seconds: 4
input_image: <file upload>
```

**Supported image formats**: JPEG, PNG, WebP
**Note**: The input image resolution must match the selected video resolution exactly.

#### Check Video Status
```bash
GET /status/{video_id}
```

#### Get Video History
```bash
GET /history
```

#### Download Video
```bash
GET /videos/{video_id}
```

#### Health Check
```bash
GET /health
```

### API Response Examples

**Generate Video Response:**
```json
{
  "video_id": "uuid-string",
  "status": "pending"
}
```

**Status Response:**
```json
{
  "video_id": "uuid-string",
  "status": "completed",
  "progress": 100,
  "video_url": "https://example.com/video.mp4",
  "revised_prompt": "Enhanced prompt used for generation"
}
```

## 🧪 Testing

Run the complete test suite:

```bash
# Run all tests
pytest tests/ -v

# Run specific test categories
pytest tests/test_azure_openai.py -v     # Unit tests
pytest tests/test_fastapi.py -v          # FastAPI tests
pytest tests/test_integration.py -v      # Integration tests

# Run with coverage
coverage run -m pytest tests/
coverage report --show-missing
```

## 🔍 Code Quality

The project uses modern Python development tools:

```bash
# Linting with Ruff
ruff check app/ tests/

# Code formatting with Black
black app/ tests/

# Import sorting with isort
isort app/ tests/

# Type checking (if mypy is added)
mypy app/
```

## 🔧 Development

### Project Structure
```
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application
│   ├── models.py            # Pydantic models
│   └── services/
│       ├── __init__.py
│       └── azure_openai.py  # Azure OpenAI service
├── static/
│   └── index.html           # Web interface
├── tests/
│   ├── conftest.py          # Test configuration
│   ├── test_azure_openai.py # Unit tests
│   ├── test_fastapi.py      # FastAPI tests
│   └── test_integration.py  # Integration tests
├── .github/workflows/
│   └── ci-cd.yml           # CI/CD pipeline
├── Dockerfile              # Multi-stage container build
├── requirements.txt        # Python dependencies
└── pyproject.toml         # Tool configuration
```

### Adding New Features

1. Create feature branch from `main`
2. Add tests first (TDD approach)
3. Implement the feature
4. Ensure all tests pass
5. Run code quality checks
6. Submit pull request

## 🚀 CI/CD Pipeline

The GitHub Actions workflow automatically:

1. **Code Quality**: Runs linting, formatting, and type checks
2. **Testing**: Executes all tests across Python 3.11 and 3.12
3. **Security**: Performs vulnerability scanning with Trivy
4. **Build**: Creates Docker image with multi-stage build
5. **Publish**: Pushes image to GitHub Container Registry
6. **Deploy**: Integration testing with built container

## 🔒 Security Features

- **Dependency scanning**: Automated vulnerability checks
- **Multi-stage builds**: Reduced attack surface in production image
- **Health checks**: Container health monitoring
- **Input validation**: Comprehensive request validation with Pydantic
- **Isolated execution**: Container runs with full control over mounted volumes to prevent permission issues

## 📊 Monitoring & Logging

- **Health endpoint**: `/health` for service monitoring
- **Structured logging**: JSON logs for production environments
- **Progress tracking**: Real-time video generation progress
- **Error handling**: Comprehensive error messages and status codes

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

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

- **Issues**: https://github.com/loryanstrant/Azure-OpenAI-Sora-webserver/issues
- **Discussions**: https://github.com/loryanstrant/Azure-OpenAI-Sora-webserver/discussions
- **Documentation**: See the `/docs` endpoint when running the application

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
- **API Endpoints**:
  - `client.videos.create()` - Start video generation
  - `client.videos.retrieve()` - Check generation status
  - `client.videos.download_content()` - Download completed video
- **Status Values**: `queued`, `in_progress`, `completed`, `failed`, `cancelled`

For more information, see the [Microsoft documentation](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/video-generation).
