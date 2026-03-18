#!/bin/bash
# Setup script for Ollama in Docker
# This script downloads the LLM model after Docker starts

set -e

echo "🚀 FlowFusion - Setting up Ollama..."

# Check if Docker is running
if ! docker-compose ps > /dev/null 2>&1; then
    echo "❌ Error: Docker containers are not running"
    echo "   Run: docker-compose up -d"
    exit 1
fi

# Wait for Ollama to be ready
echo "⏳ Waiting for Ollama to start..."
for i in {1..30}; do
    if docker-compose exec -T ollama curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo "✅ Ollama is ready"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "❌ Ollama failed to start"
        exit 1
    fi
    sleep 2
done

# Check if model is already installed
echo "📦 Checking for llama3.2 model..."
if docker-compose exec -T ollama ollama list | grep -q "llama3.2"; then
    echo "✅ llama3.2 already installed"
else
    echo "⬇️  Downloading llama3.2 model (this may take 5-10 minutes)..."
    docker-compose exec -T ollama ollama pull llama3.2
    echo "✅ llama3.2 downloaded"
fi

echo ""
echo "🎉 Setup complete!"
echo ""
echo "To enable AI summaries, update .env:"
echo "  AI_AUTO_GENERATE=true"
echo ""
echo "Then restart the worker:"
echo "  docker-compose restart worker"
echo ""
