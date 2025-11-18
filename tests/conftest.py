"""Test configuration and fixtures."""

import tempfile
from unittest.mock import patch

import pytest


@pytest.fixture
def temp_storage_dir():
    """Create a temporary storage directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def mock_env_vars(temp_storage_dir):
    """Mock environment variables for testing."""
    with patch.dict(
        "os.environ",
        {
            "AZURE_OPENAI_API_KEY": "test-api-key",
            "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com/",
            "AZURE_OPENAI_DEPLOYMENT": "sora-2",
            "VIDEO_STORAGE_DIR": temp_storage_dir,
        },
    ):
        yield
