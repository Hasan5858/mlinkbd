#!/bin/bash

# Deploy Cloudflare Worker
echo "🚀 Deploying Cloudflare Worker..."

# Check if wrangler is installed
if ! command -v wrangler &> /dev/null; then
    echo "❌ Wrangler CLI not found. Installing..."
    npm install -g wrangler
fi

# Deploy the worker
echo "📦 Deploying to Cloudflare..."
wrangler deploy

echo "✅ Deployment complete!"
echo "🌐 Your worker is available at: https://mlinkbd-proxy.hasansarker58.workers.dev/"
