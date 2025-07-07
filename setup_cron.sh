#!/bin/bash

# Get the absolute path to the project directory
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Create log directory if it doesn't exist
mkdir -p "$PROJECT_DIR/logs"

# Check if .venv exists
if [ ! -d "$PROJECT_DIR/.venv" ]; then
    echo "Error: Virtual environment not found at $PROJECT_DIR/.venv"
    echo "Please create it first with: python3 -m venv .venv"
    exit 1
fi

# Add cron job using the virtual environment's Python
(crontab -l 2>/dev/null; echo "*/15 * * * * cd $PROJECT_DIR && $PROJECT_DIR/.venv/bin/python src/scraper.py >> $PROJECT_DIR/logs/minecraft_scraper.log 2>&1") | crontab -

echo "Cron job added successfully!"
echo "Using Python from: $PROJECT_DIR/.venv/bin/python"
echo "Logs will be written to: $PROJECT_DIR/logs/minecraft_scraper.log"