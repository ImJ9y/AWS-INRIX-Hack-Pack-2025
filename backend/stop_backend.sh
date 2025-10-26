#!/bin/bash

# Fall Detection Backend Stop Script
# Stops the backend server

echo "🛑 Stopping Fall Detection Backend..."
echo "==================================="

# Check if backend is running
if pgrep -f "simple_backend.py" > /dev/null; then
    PID=$(pgrep -f "simple_backend.py")
    echo "Found running backend (PID: $PID)"
    
    # Kill the process
    pkill -f "simple_backend.py"
    
    # Wait for it to stop
    sleep 1
    
    # Verify it stopped
    if ! pgrep -f "simple_backend.py" > /dev/null; then
        echo "✅ Backend stopped successfully!"
    else
        echo "⚠️  Force killing backend..."
        pkill -9 -f "simple_backend.py"
        echo "✅ Backend forcefully stopped!"
    fi
else
    echo "ℹ️  Backend is not running"
fi
