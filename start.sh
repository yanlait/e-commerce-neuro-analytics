#!/bin/bash
cd "$(dirname "$0")"

echo "Starting Langfuse..."
docker compose -f docker/docker-compose.yml up -d

echo "Waiting for Langfuse..."
until curl -s http://localhost:3001/api/public/health > /dev/null; do sleep 2; done
echo "Langfuse ready"

echo "Starting bot..."
python bot/main.py &
BOT_PID=$!
echo "Bot PID: $BOT_PID"

echo ""
echo "All services running:"
echo "  Langfuse: http://localhost:3001"
echo "  Bot PID:  $BOT_PID"
echo ""
echo "Press Ctrl+C to stop"

wait $BOT_PID
