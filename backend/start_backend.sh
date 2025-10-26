#!/bin/bash

# Fall Detection Backend Startup Script
# Automatically starts the backend server

echo "Starting Fall Detection Backend..."
echo "=================================="

# Navigate to backend directory
cd "$(dirname "$0")"

# Check if backend is already running
if pgrep -f "simple_backend.py" > /dev/null; then
    echo "Backend is already running!"
    echo "   PID: $(pgrep -f 'simple_backend.py')"
    exit 1
fi

# Start the backend
echo "Starting backend server on port 5001..."
python3 simple_backend.py &

# Wait a moment for server to start
sleep 2

# Check if it started successfully
if pgrep -f "simple_backend.py" > /dev/null; then
    echo "Backend started successfully!"
    echo "   PID: $(pgrep -f 'simple_backend.py')"
    echo "   URL: http://localhost:5001"
    echo ""
    echo "Access the API at:"
    echo "   - Status: http://localhost:5001/api/status"
    echo "   - Latest Frame: http://localhost:5001/api/latest_frame"
    echo ""
    echo "To stop the backend, run: ./stop_backend.sh"
else
    echo "Failed to start backend!"
    exit 1
fi
