#!/bin/sh
# Entrypoint script to handle volume mount permissions

set -e

# Function to fix directory permissions
fix_permissions() {
    local dir="$1"
    
    # Check if directory exists
    if [ -d "$dir" ]; then
        echo "Checking permissions for $dir..."
        
        # If running as root, ensure appuser owns the directory
        if [ "$(id -u)" -eq 0 ]; then
            # Get current owner UID
            current_owner=$(stat -c '%u' "$dir")
            appuser_uid=$(id -u appuser)
            
            # If directory is not owned by appuser, fix it
            if [ "$current_owner" != "$appuser_uid" ]; then
                echo "Fixing permissions for $dir (current owner: $current_owner, target: $appuser_uid)..."
                chown -R appuser:appuser "$dir" 2>/dev/null || {
                    echo "Warning: Could not change ownership of $dir"
                    echo "Files may not be accessible by the application"
                }
                chmod -R 755 "$dir" 2>/dev/null || true
                echo "Permissions fixed for $dir"
            else
                echo "Directory $dir already owned by appuser"
            fi
        fi
        
        # Create videos subdirectory if it doesn't exist
        if [ "$(id -u)" -eq 0 ]; then
            mkdir -p "$dir/videos" 2>/dev/null || true
            chown appuser:appuser "$dir/videos" 2>/dev/null || true
        else
            mkdir -p "$dir/videos" 2>/dev/null || true
        fi
    fi
}

# Fix permissions for data directory and subdirectories
fix_permissions "/app/data"

# If running as root, switch to appuser and execute command
if [ "$(id -u)" -eq 0 ]; then
    echo "Switching to appuser and starting application..."
    # Switch to appuser and run the command
    exec gosu appuser "$@"
else
    # Already running as non-root user, just execute command
    echo "Already running as non-root user, starting application..."
    exec "$@"
fi
