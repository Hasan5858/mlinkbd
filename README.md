# MovieLinkBD API Service

A high-performance API service for streaming movies and TV shows from MovieLinkBD with ad-free video playback, multiple version selection, and intelligent caching.

## Features

- 🎬 **Ad-Free Video Streaming** - Clean video player without ads
- 🚀 **Immediate Loading** - Video player loads instantly with progress tracking
- 📊 **Progress Percentage** - Real-time loading progress with status messages
- 🔄 **Multiple Versions** - Select from different quality/language versions
- ⚡ **Smart Caching** - 2-hour video cache, 30-minute search cache
- 🌐 **Cloudflare Integration** - Video proxying through Cloudflare Workers
- 📱 **Responsive Design** - Works on all devices
- 🎯 **Season-Aware Matching** - Intelligent TV series episode matching

## API Endpoints

- `GET /api/{tmdb_id}` - Stream movie by TMDB ID
- `GET /api/{tmdb_id}/{season}/{episode}` - Stream TV episode
- `GET /api/scrape/{tmdb_id}` - Background scraping for movies
- `GET /api/scrape/{tmdb_id}/{season}/{episode}` - Background scraping for TV
- `GET /api/health` - Health check
- `GET /search` - Search interface

## Environment Variables

- `TMDB_API_KEY` - The Movie Database API key (required)

## Deployment

### Vercel Deployment

1. Install Vercel CLI:
   ```bash
   npm install -g vercel
   ```

2. Deploy to Vercel:
   ```bash
   vercel --prod
   ```

3. Set environment variables in Vercel dashboard:
   - `TMDB_API_KEY` - Your TMDB API key

### Cloudflare Worker (Video Proxy)

The video proxy is deployed separately to Cloudflare Workers:

1. Install Wrangler CLI:
   ```bash
   npm install -g wrangler
   ```

2. Deploy the worker:
   ```bash
   wrangler deploy
   ```

## Architecture

- **Frontend**: Vercel (API and web interface)
- **Video Proxy**: Cloudflare Workers
- **Caching**: In-memory with TTL
- **Video Player**: JWPlayer with HTML5 fallback

## Performance

- **First Load**: ~3-5 seconds (scraping + loading)
- **Cached Load**: ~0.5 seconds (instant from cache)
- **Cache Duration**: 2 hours for video, 30 minutes for search

## Security

- Domain validation for video sources
- CORS headers properly configured
- Input sanitization and validation
- Rate limiting through Vercel

## License

MIT License