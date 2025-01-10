#!/bin/bash

# Navigate to the project directory
cd "$(dirname "$0")"

# GitHub credentials
GITHUB_USERNAME="your_username"
GITHUB_PERSONAL_ACCESS_TOKEN="your_token"

# Construct the GitHub URL with credentials
GITHUB_URL="https://${GITHUB_USERNAME}:${GITHUB_PERSONAL_ACCESS_TOKEN}@github.com/hoganSean99/StudentTimeAndAttendance.git"

# Pull the newest version from GitHub
echo "Pulling the latest version from GitHub..."
git pull $GITHUB_URL main

# Start the Flask app
echo "Starting the Flask app..."
export FLASK_APP=app.py
flask run &

# Get the local server URL
URL="http://127.0.0.1:5000"

# Wait for the server to start
sleep 2

# Open the default browser to the Flask app
echo "Opening the browser..."
open $URL
