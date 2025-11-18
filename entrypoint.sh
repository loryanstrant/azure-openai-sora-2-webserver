#!/bin/sh
# Entrypoint script to handle volume mount permissions for Azure OpenAI Sora Web Server

set -e

# Function to ensure directory exists and is accessible
setup_directories() {
    local dir="$1"
    
    # Create directory and subdirectories if they don't exist
    if [ ! -d "$dir" ]; then
        echo "Creating directory $dir..."
        mkdir -p "$dir/videos" 2>/dev/null || {
            echo "Warning: Could not create $dir - this may be expected if running as non-root"
        }
    else
        echo "Directory $dir exists"
        # Ensure videos subdirectory exists
        mkdir -p "$dir/videos" 2>/dev/null || true
    fi
    
    # Ensure directory is writable
    if [ -w "$dir" ]; then
        echo "Directory $dir is writable"
    else
        echo "Warning: Directory $dir may not be writable. Please ensure volume mount has correct permissions (UID/GID 1000)."
    fi
}

# Setup data directory and subdirectories
setup_directories "/app/data"

echo "Starting application as appuser (UID 1000)..."
exec "$@"

